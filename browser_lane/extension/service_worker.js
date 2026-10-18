"use strict";

/* MV3 extension: owns only tabs it creates. Never controls the active tab.
 * Only fixed actions via the dedicated native host; no eval, page-script text,
 * global keyboard shortcuts or Chrome profile crawling.
 */
const HOST = "com.semanticbridge.browserlane";
const GROUP_TITLE = "Semantic Bridge — Agent";
let port = null;

function validUrl(url) {
  if (typeof url !== "string" || url.length > 2048) throw Error("INVALID_URL");
  const u = new URL(url);
  if (!["http:", "https:"].includes(u.protocol) || u.username || u.password)
    throw Error("URL_NOT_ALLOWED");
  return u.href;
}
function validSelector(selector) {
  if (typeof selector !== "string" || !selector.length || selector.length > 1000 ||
      /[\u0000-\u001f]/.test(selector) || selector !== selector.trim())
    throw Error("INVALID_SELECTOR");
  return selector;
}
async function owned() {
  const data = await chrome.storage.local.get("semanticBridgeOwned");
  return data.semanticBridgeOwned || { groupId: -1, tabIds: [] };
}
async function save(data) {
  await chrome.storage.local.set({ semanticBridgeOwned: data });
}
async function tabFor(tabId) {
  if (!Number.isInteger(tabId) || tabId < 1) throw Error("INVALID_TAB");
  const data = await owned();
  if (!data.tabIds.includes(tabId)) throw Error("TAB_NOT_OWNED");
  let tab = await chrome.tabs.get(tabId);
  if (tab.groupId !== data.groupId) throw Error("TAB_MOVED_OUT_OF_AGENT_GROUP");
  if (!/^https?:\/\//.test(tab.url || tab.pendingUrl || "")) throw Error("PROTECTED_TAB");
  // A collapsed tab group freezes its pages. Uncollapse only this owned
  // group; this never activates a tab or brings Chrome to the foreground.
  const group=await chrome.tabGroups.get(data.groupId);
  if (group.collapsed) await chrome.tabGroups.update(data.groupId,{collapsed:false});
  for (let attempt=0;attempt<15;attempt++) {
    tab=await chrome.tabs.get(tabId);
    if (tab.groupId !== data.groupId) throw Error("TAB_MOVED_OUT_OF_AGENT_GROUP");
    if (tab.discarded) throw Error("AGENT_TAB_DISCARDED");
    if (!tab.frozen) return { tab, data };
    await new Promise(resolve=>setTimeout(resolve,100));
  }
  throw Error("AGENT_TAB_STILL_FROZEN");
}
async function openBackground(url) {
  url = validUrl(url);
  const data = await owned();
  let winId;
  if (data.groupId >= 0) {
    try {
      const group = await chrome.tabGroups.get(data.groupId);
      winId = group.windowId;
    } catch { data.groupId = -1; data.tabIds = []; }
  }
  if (!winId) {
    const win = await chrome.windows.getLastFocused({ windowTypes: ["normal"] });
    if (!win || !Number.isInteger(win.id)) throw Error("NO_EXISTING_CHROME_WINDOW");
    winId = win.id;
  }
  const tab = await chrome.tabs.create({ windowId: winId, url, active: false });
  try {
    // Prevent Memory Saver from discarding our inactive group pages.
    // This never activates the tab or changes the focused window.
    await chrome.tabs.update(tab.id, {autoDiscardable:false});
    const groupId = await chrome.tabs.group({
      tabIds: [tab.id],
      ...(data.groupId >= 0 ? {groupId:data.groupId} : {})
    });
    await chrome.tabGroups.update(groupId, {
      title: GROUP_TITLE, color: "blue", collapsed: false
    });
    data.groupId = groupId;
    data.tabIds.push(tab.id);
    await save(data);
    return { tab_id: tab.id, group_id:groupId, background: true, url };
  } catch (e) {
    await chrome.tabs.remove(tab.id);
    throw e;
  }
}
// Chrome may freeze an inactive renderer during execution. A bounded result
// is required; for write actions, a timeout means UNKNOWN OUTCOME (no retry).
async function boundedExecuteScript(injection) {
  let timer;
  const timeout=new Promise((_,reject)=>{
    timer=setTimeout(()=>reject(Error("CHROME_SCRIPT_TIMEOUT_OUTCOME_UNKNOWN")),5500);
  });
  try {
    return await Promise.race([chrome.scripting.executeScript(injection),timeout]);
  } finally {
    clearTimeout(timer);
  }
}
async function readPage(tabId) {
  await tabFor(tabId);
  // Reading is idempotent: retry only when Chrome replaces the main
  // frame during a background navigation. Never retry clicks automatically.
  let result;
  for (let attempt=0;attempt<3;attempt++) {
    try {
      result = await boundedExecuteScript({
    target: {tabId},
    func: () => ({
      title: document.title,
      url: location.href,
      text:(document.body?.innerText||"").slice(0,12000),
      fields: Array.from(document.querySelectorAll("input,textarea,button,select"))
        .slice(0,60).map(x => ({
          tag:x.tagName.toLowerCase(), id:x.id||"", name:x.name||"",
          type:x.type||"", label:x.getAttribute("aria-label")||"",
          text:(x.innerText||"").slice(0,80)
        }))
    })
  });
      break;
    } catch (e) {
      if (attempt===2 || !/Frame with ID 0 was removed|No frame with id|Cannot access contents/.test(String(e)))
        throw e;
      const {tab}=await tabFor(tabId);
      if (tab.discarded || tab.frozen) throw Error("BACKGROUND_TAB_SUSPENDED");
      await new Promise(resolve=>setTimeout(resolve,150*(attempt+1)));
    }
  }
  if (!result[0] || !result[0].result) throw Error("DOCUMENT_INACCESSIBLE");
  return {tab_id:tabId, ...result[0].result};
}
async function fillPage(tabId, selector, value) {
  await tabFor(tabId);
  validSelector(selector);
  if (typeof value !== "string" || value.length > 10000) throw Error("INVALID_VALUE");
  const result = await boundedExecuteScript({
    target:{tabId}, args:[selector,value],
    func:(sel,val) => {
      const hits=document.querySelectorAll(sel);
      if (hits.length!==1) return {verified:false,reason:"AMBIGUOUS_OR_MISSING"};
      const el=hits[0];
      if (el.disabled || el.readOnly ||
          !["INPUT","TEXTAREA"].includes(el.tagName))
        return {verified:false};
      const proto=el.tagName==="INPUT"?HTMLInputElement.prototype:HTMLTextAreaElement.prototype;
      Object.getOwnPropertyDescriptor(proto,"value").set.call(el,val);
      el.dispatchEvent(new Event("input",{bubbles:true}));
      el.dispatchEvent(new Event("change",{bubbles:true}));
      return {verified:el.value===val};
    }
  });
  if (!result[0]?.result?.verified) throw Error("POSTCONDITION_FAILED");
  return {tab_id:tabId,verified:true};
}
async function clickPage(tabId, selector) {
  await tabFor(tabId);
  validSelector(selector);
  const result=await boundedExecuteScript({
    target:{tabId},args:[selector],
    func:sel=>{
      const hits=document.querySelectorAll(sel);
      if (hits.length!==1) return false;
      const el=hits[0];
      if (el.disabled) return false;
      el.click();
      return true;
    }
  });
  if (!result[0]?.result) throw Error("ELEMENT_NOT_FOUND");
  return {tab_id:tabId,invoked:true};
}
async function dispatch(command) {
  switch(command.op) {
    case "status": {
      const data=await owned();
      let collapsed=null;
      if (data.groupId>=0) {
        try { collapsed=(await chrome.tabGroups.get(data.groupId)).collapsed; }
        catch { collapsed=null; }
      }
      return {connected:true,group_id:data.groupId,
              owned_tab_count:data.tabIds.length,group_collapsed:collapsed,worker_version:"0.2.2"};
    }
    case "park": {
      const state=await owned();
      if (state.groupId<0 || !state.tabIds.length) return {parked:false};
      // Only our own group; do not change active tab or focused window.
      await chrome.tabGroups.update(state.groupId,{collapsed:true});
      return {parked:true,group_id:state.groupId};
    }
    case "open": return openBackground(command.url);
    case "list": {
      const state=await owned();
      const tabs=[];
      for (const id of state.tabIds) {
        try {
          const {tab}=await tabFor(id);
          tabs.push({tab_id:id,title:tab.title||"",url:tab.url||""});
        } catch {}
      }
      return tabs;
    }
    case "read":return readPage(command.tab_id);
    case "fill":return fillPage(command.tab_id,command.selector,command.value);
    case "click":return clickPage(command.tab_id,command.selector);
    case "navigate": {
      await tabFor(command.tab_id);
      await chrome.tabs.update(command.tab_id,{url:validUrl(command.url)});
      return {tab_id:command.tab_id,url:command.url};
    }
    case "close": {
      const {data}=await tabFor(command.tab_id);
      await chrome.tabs.remove(command.tab_id);
      data.tabIds=data.tabIds.filter(t=>t!==command.tab_id);
      if (!data.tabIds.length) data.groupId=-1;
      await save(data);
      return {closed:command.tab_id};
    }
    case "close_all": {
      const data=await owned();
      let count=0;
      for (const id of data.tabIds) {
        try {await tabFor(id);await chrome.tabs.remove(id);count++;}catch {}
      }
      await save({groupId:-1,tabIds:[]});
      return {closed_count:count};
    }
    default:throw Error("UNKNOWN_OPERATION");
  }
}
function connectNative() {
  if (port) return;
  let peer;
  try {
    peer=chrome.runtime.connectNative(HOST);
    port=peer;
  } catch {port=null;return;}
  peer.onMessage.addListener(async msg => {
    if (msg.type !== "command" || typeof msg.id !== "string") return;
    try {
      const result=await dispatch(msg);
      peer.postMessage({id:msg.id,ok:true,result});
    } catch(e) {
      peer.postMessage({id:msg.id,ok:false,error:String(e.message||e).slice(0,160)});
    }
  });
  peer.onDisconnect.addListener(() => {if (port===peer) port=null;});
}
connectNative();
// A disconnected host never forces Chrome focus or spins in a retry loop.
// Chrome wakes the MV3 worker to reconnect periodically.
chrome.alarms.create("sb-native-reconnect",{periodInMinutes:1}).catch(()=>{});
chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name==="sb-native-reconnect" && port===null) connectNative();
});
chrome.runtime.onStartup.addListener(connectNative);
chrome.runtime.onInstalled.addListener(connectNative);
