"use strict";
const fs=require("fs"),vm=require("vm"),assert=require("assert"),path=require("path");
const source=fs.readFileSync(path.join(__dirname,"..","extension","service_worker.js"),"utf8");
let group={id:1,windowId:2,collapsed:false};
const chrome={
 storage:{local:{get:async()=>({semanticBridgeOwned:{groupId:1,tabIds:[50]}}),set:async()=>{}}},
 tabs:{get:async()=>({id:50,groupId:1,url:"https://example.com",frozen:false,discarded:false})},
 tabGroups:{get:async()=>group,update:async()=>{}},
 scripting:{executeScript:()=>new Promise(()=>{})},
 runtime:{connectNative:()=>({onMessage:{addListener:()=>{}},onDisconnect:{addListener:()=>{}}}),onStartup:{addListener:()=>{}},onInstalled:{addListener:()=>{}}},
 alarms:{create:()=>Promise.resolve(),onAlarm:{addListener:()=>{}}}
};
// Accelerate the fixed command deadline in the deterministic test.
const context=vm.createContext({chrome,console,URL,Promise,Error,
 setTimeout:(callback,ms)=>setTimeout(callback,5),clearTimeout});
vm.runInContext(source,context);
(async()=>{
 const outcome=await Promise.race([
   vm.runInContext('dispatch({op:"read",tab_id:50})',context)
      .then(()=>({unexpected:true}),err=>({error:String(err)})),
   new Promise(resolve=>setTimeout(()=>resolve({testTimeout:true}),200))
 ]);
 assert(!outcome.testTimeout,"extension must bound a suspended Chrome executeScript");
 assert(!outcome.unexpected,"pending script may not report success");
 assert(/SCRIPT_TIMEOUT|UNKNOWN_OUTCOME/.test(outcome.error),outcome.error);
 console.log("PENDING_SCRIPT_TIMEOUT_GATE_PASS");
})().catch(err=>{console.error(err.stack||err);process.exitCode=1});
