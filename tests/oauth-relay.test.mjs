import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const load=async p=>(await import('data:text/javascript;base64,'+Buffer.from(await readFile(new URL(p,import.meta.url))).toString('base64'))).default;
const connect=await load('../api/meta/connect.js'), callback=await load('../api/meta/callback.js');
function response(){return {headers:{},setHeader(k,v){this.headers[k]=v},status(s){this.code=s;return this},json(v){this.body=v;return this},send(v){this.body=v;return this},redirect(s,u){this.code=s;this.location=u;return this}}}
process.env.VITE_API_BASE_URL='https://synthetic.invalid';
process.env.OAUTH_CALLBACK_TARGET='https://synthetic.invalid/api/meta/oauth/callback';
test('connect relays directly to Instagram without following authorization',async()=>{
 globalThis.fetch=async(u,o)=>{assert.equal(u,'https://synthetic.invalid/api/meta/oauth/start');assert.equal(o.redirect,'manual');return new Response(null,{status:307,headers:{location:'https://www.instagram.com/oauth/authorize?state=synthetic'}})};
 const r=response();await connect({},r);assert.equal(r.code,302);assert.match(r.location,/^https:\/\/www.instagram.com\//);assert.equal(r.headers['Cache-Control'],'no-store');
});
test('connect forwards the selected app and reports unknown apps',async()=>{
 globalThis.fetch=async(url)=>{
  assert.equal(url,'https://synthetic.invalid/api/meta/oauth/start?app=app-2');
  return new Response('private detail',{status:404});
 };
 const r=response();await connect({query:{app:'app-2',secret:'ignored'}},r);
 assert.equal(r.code,404);assert.equal(r.body.detail,'App Meta não encontrado.');
});
test('connect rejects ambiguous or malformed app selectors',async()=>{
 globalThis.fetch=async()=>assert.fail('Unexpected upstream request');
 for (const app of [['app-1','app-2'],'app-02','']) {
  const r=response();await connect({query:{app}},r);assert.equal(r.code,400);
 }
});
test('connect rejects unrelated redirects and does not expose upstream detail',async()=>{
 globalThis.fetch=async()=>new Response('secret synthetic detail',{status:302,headers:{location:'https://untrusted.invalid'}});
 const r=response();await connect({},r);assert.equal(r.code,502);assert.ok(!JSON.stringify(r).includes('secret'));
});
test('connect failure remains on the public domain',async()=>{
 globalThis.fetch=async()=>{throw new Error('synthetic private error')};const r=response();await connect({},r);assert.equal(r.code,502);assert.equal(r.location,undefined);
});
test('callback forwards only scalar allowed parameters and preserves HTML status',async()=>{
 globalThis.fetch=async(u,o)=>{assert.equal(u.searchParams.get('code'),'synthetic');assert.equal(u.searchParams.get('state'),'synthetic');assert.equal(u.searchParams.has('other'),false);assert.equal(u.searchParams.has('error'),false);assert.equal(o.redirect,'manual');return new Response('<h2>synthetic invalid state</h2>',{status:400,headers:{'content-type':'text/html'}})};
 const r=response();await callback({query:{code:'synthetic',state:'synthetic',other:'ignore',error:['ignore']}},r);assert.equal(r.code,400);assert.equal(r.body,'<h2>synthetic invalid state</h2>');assert.equal(r.location,undefined);
});
test('callback timeout neither leaks details nor retries a consumed code',async()=>{
 let calls=0;globalThis.fetch=async()=>{calls++;throw new Error('private')};const r=response();await callback({query:{state:'synthetic'}},r);assert.equal(r.code,502);assert.equal(calls,1);assert.ok(!r.body.includes('private'));
});
test('callback rejects backend redirects instead of forwarding API hop',async()=>{
 globalThis.fetch=async()=>new Response(null,{status:302,headers:{location:'https://synthetic.invalid'}});const r=response();await callback({query:{}},r);assert.equal(r.code,502);assert.equal(r.location,undefined);
});
