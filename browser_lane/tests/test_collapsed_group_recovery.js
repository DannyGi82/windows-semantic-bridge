// Deterministic regression: Chrome suspends scripting.executeScript when a group is collapsed.
"use strict";
const fs = require("fs"), vm=require("vm"), assert=require("assert");
const worker=fs.readFileSync(require("path").join(__dirname,"..","extension","service_worker.js"),"utf8");
let storage={semanticBridgeOwned:{groupId:7,tabIds:[100]}};
const group={id:7,collapsed:true,title:"Semantic Bridge — Agent",windowId:5};
const calls=[];
const fakePort={
  onMessage:{addListener:()=>{}},
  onDisconnect:{addListener:()=>{}},
  postMessage:()=>{}
};
const chrome={
  storage:{local:{
    get:async()=>storage,
    set:async data=>{storage={...storage,...data};}
  }},
  tabs:{
    get:async id=>({id,groupId:7,url:"https://example.com/",title:"Tab"}),
    create:async opts=>{assert.strictEqual(opts.active,false);return {id:101};},
    group:async opts=>7,
    update:async()=>{},
    remove:async()=>{}
  },
  tabGroups:{
    get:async()=>({...group}),
    update:async(id,props)=>{assert.strictEqual(id,7);Object.assign(group,props);calls.push(props);}
  },
  scripting:{executeScript:async()=>{
    if(group.collapsed) return new Promise(()=>{});
    return [{result:{title:"QA",text:"LIVE",url:"https://example.com/",fields:[]}}];
  }},
  runtime:{
    connectNative:()=>fakePort,
    onStartup:{addListener:()=>{}},
    onInstalled:{addListener:()=>{}}
  },
  alarms:{create:()=>Promise.resolve(),onAlarm:{addListener:()=>{}}},
  windows:{getLastFocused:async()=>({id:5})}
};
const context=vm.createContext({chrome,console,URL,Promise,Error,setTimeout,clearTimeout});
vm.runInContext(worker,context);
function bounded(promise) {
 return Promise.race([
   promise,new Promise((resolve)=>setTimeout(()=>resolve("TIMEOUT_FROZEN"),400))
 ]);
}
(async()=>{
 const read=await bounded(vm.runInContext('dispatch({op:"read",tab_id:100})',context));
 assert.notStrictEqual(read,"TIMEOUT_FROZEN","background group must unfreeze before DOM reads");
 assert.strictEqual(read.text,"LIVE");
 assert.strictEqual(group.collapsed,false);
 storage={semanticBridgeOwned:{groupId:-1,tabIds:[]}};
 const opened=await bounded(vm.runInContext('dispatch({op:"open",url:"https://example.com"})',context));
 assert.notStrictEqual(opened,"TIMEOUT_FROZEN");
 assert.strictEqual(group.collapsed,false,"new agent group cannot be collapsed mid-task");
 assert.strictEqual(opened.background,true);
 const parked=await bounded(vm.runInContext('dispatch({op:"park"})',context));
 assert(parked.parked);
 assert.strictEqual(group.collapsed,true,"idle agent group must collapse");
 const revived=await bounded(vm.runInContext('dispatch({op:"read",tab_id:101})',context));
 assert.notStrictEqual(revived,"TIMEOUT_FROZEN","next operation must reopen parked group");
 assert.strictEqual(group.collapsed,false);

 console.log("GROUP_FREEZE_REGRESSION_PASS");
})().catch(e=>{console.error(e.stack||e);process.exitCode=1});