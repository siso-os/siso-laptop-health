import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { submit, validateHello } from '../bin/health-owner.mjs';
const root = fs.mkdtempSync(path.join(os.tmpdir(), '.siso-health-owner-'));
const originalWS = globalThis.WebSocket;
try {
  const home=path.join(root,'home');fs.mkdirSync(path.join(home,'.agents'),{recursive:true});
  const hostPath=path.join(root,'host.json');
  const host={name:'HEALTH',port:1234,token:'fixture-private-token',session:'s1',cwd:home,state:'idle',child:'running'};
  fs.writeFileSync(hostPath,JSON.stringify(host),{mode:0o600});
  const hello={t:'hello',name:'HEALTH',session:'s1',state:'idle',child:'running',queue:{held:false,entries:[]},capabilities:{version:1,activeTurnId:null,compacting:false},pendingQuestions:[],tasks:[]};
  let caseId=0,frame=hello,receipt='saved',duplicate=false,transportError=false,sends=[];
  class FakeWS {
    constructor(){this.listeners={};setTimeout(()=>{this.emit('message',{data:JSON.stringify(frame)});if(duplicate)this.emit('message',{data:JSON.stringify(frame)});},0);}
    addEventListener(k,f){(this.listeners[k]??=[]).push(f);}
    emit(k,v){for(const f of this.listeners[k]??[])f(v);}
    send(raw){const m=JSON.parse(raw);sends.push(m);setTimeout(()=>this.emit(transportError?'error':'message',transportError?{}:{data:JSON.stringify({t:'prompt.receipt',key:m.key,id:m.messageId,phase:receipt,queueRevision:1})}),0);}
    close(){}
  }
  globalThis.WebSocket=FakeWS;
  const policy=()=>({enabled:true,home,hostPath,statePath:path.join(root,`state-${++caseId}.json`),cadence_seconds:1800});
  for(const bad of [
    {...hello,queue:undefined}, {...hello,capabilities:{}}, {...hello,pendingQuestions:undefined},
    {...hello,queue:{held:false}}, {...hello,queue:{held:true,entries:[]}},
    {...hello,queue:{held:false,entries:[{phase:'saved'}]}},
    {...hello,queue:{held:false,entries:[{phase:'nonsense'}]}},
    {...hello,capabilities:{...hello.capabilities,activeTurnId:'turn'}},
    {...hello,capabilities:{...hello.capabilities,compacting:true}},
    {...hello,pendingQuestions:[{id:'q'}]}, {...hello,tasks:[{status:'pending'}]},
  ])assert.throws(()=>validateHello(bad));
  validateHello({...hello,queue:{held:false,entries:[{phase:'accepted'},{phase:'started'},{phase:'cancelled'}]},tasks:[{status:'done'},{status:'failed'}]});
  const p=policy();const first=await submit(p);
  assert.equal(first.phase,'saved');assert.equal(first.ok,true);assert.equal(sends.length,1);
  assert.equal(sends[0].delivery,'next');assert.match(sends[0].text,/\.agents\/role-health-ledger\.jsonl/);assert.match(sends[0].text,/HANDOFF.md last/);
  const state=JSON.parse(fs.readFileSync(p.statePath));assert.equal(state.phase,'saved');assert.ok(state.cooldownUntil>state.at);
  assert.equal((await submit(p)).reason,'cooldown');assert.equal(sends.length,1);
  fs.writeFileSync(hostPath,JSON.stringify({...host,state:'working'}));
  frame={...hello,state:'working',capabilities:{...hello.capabilities,activeTurnId:'current-turn'}};
  duplicate=true;const bootstrap=await submit(policy(),{enqueueNext:true});assert.equal(bootstrap.ok,true);assert.equal(sends.length,2);
  assert.equal((await submit(policy())).reason,'host not idle');
  fs.writeFileSync(hostPath,JSON.stringify(host));duplicate=false;frame={...hello,queue:undefined,capabilities:undefined,pendingQuestions:undefined};
  const legacy=await submit(policy());assert.equal(legacy.reason,'unsupported-protocol');assert.equal(legacy.phase,'blocked');assert.equal(sends.length,2);
  frame=hello;transportError=true;const ambPolicy=policy();const ambiguous=await submit(ambPolicy);assert.equal(ambiguous.phase,'ambiguous');
  const ambState=JSON.parse(fs.readFileSync(ambPolicy.statePath));ambState.cooldownUntil=0;ambState.key='old-slot';fs.writeFileSync(ambPolicy.statePath,JSON.stringify(ambState));
  const sentBefore=sends.length;assert.equal((await submit(ambPolicy)).reason,'unreconciled');assert.equal(sends.length,sentBefore);
  transportError=false;receipt='failed';assert.equal((await submit(policy())).phase,'failed');
  receipt='unknown';assert.equal((await submit(policy())).phase,'ambiguous');
  const corruptPolicy=policy();fs.writeFileSync(corruptPolicy.statePath,'fixture-private-token');assert.equal((await submit(corruptPolicy)).reason,'state unavailable');
  fs.writeFileSync(hostPath,'{"token":"fixture-private-token",BROKEN');const malformed=await submit(policy());assert.ok(!JSON.stringify(malformed).includes('fixture-private-token'));
  fs.writeFileSync(hostPath,JSON.stringify(host));fs.chmodSync(hostPath,0o644);assert.equal((await submit(policy())).reason,'host permissions');
  fs.chmodSync(hostPath,0o600);fs.writeFileSync(hostPath,JSON.stringify({...host,port:65536}));assert.equal((await submit(policy())).ok,false);
  console.log('ok: exact HELLO, saved receipt, next delivery, bootstrap, duplicate prevention, legacy refusal, uncertain-send lock, failed/unknown receipts, private errors and permissions');
} finally { globalThis.WebSocket=originalWS;fs.rmSync(root,{recursive:true}); }
