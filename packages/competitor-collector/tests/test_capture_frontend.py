"""Frontend contract and account-boundary checks without ADB or browser writes."""
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest


STATIC = Path(__file__).resolve().parents[1] / "competitor_collector" / "static"


def test_capture_markup_has_unique_ids_and_all_script_targets():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    ids = re.findall(r'\bid="([^"]+)"', html)
    assert len(ids) == len(set(ids))
    source = (STATIC / "screens.js").read_text(encoding="utf-8")
    targets = set(re.findall(r'\$\("([^"]+)"\)', source))
    assert targets <= set(ids)
    assert '<script src="/screens.js" defer></script>' in html
    assert "不会一键遍历整个 App" in html
    assert "商店宣传图" in html


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js is needed for browser-independent JS checks")
@pytest.mark.parametrize("name", ["app.js", "screens.js"])
def test_capture_javascript_syntax(name):
    subprocess.run([shutil.which("node"), "--check", str(STATIC / name)], check=True, capture_output=True, text=True)


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js is needed for browser-independent JS checks")
def test_capture_explicit_operations_and_account_reset():
    # Small DOM fixture exercises real event handlers, not a duplicate implementation.
    harness = r'''
const fs = require("fs"), vm = require("vm"), assert = require("assert");
const html = fs.readFileSync(STATIC + "/index.html", "utf8");
const all = [], elements = new Map();
class El {
  constructor(tag = "div", id = "") {
    this.tagName = tag.toUpperCase(); this.id = id; this.children = [];
    this.listeners = {}; this.dataset = {}; this.hidden = false; this.disabled = false;
    this.value = ""; this.attributes = {}; this.textContent = ""; this.src = "";
    this.classList = { add(){}, remove(){}, toggle(){} }; all.push(this);
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; if (this.tagName === "SELECT") this.value = children[0]?.value || ""; }
  addEventListener(event, fn) { (this.listeners[event] ||= []).push(fn); }
  setAttribute(key,value) { this.attributes[key] = value; }
  removeAttribute(key) { delete this.attributes[key]; if (key === "src") this.src = ""; }
  querySelectorAll(selector) {
    const children = this.children.flatMap(child => child instanceof El ? [child, ...child.querySelectorAll("*")] : []);
    return selector === "button" ? children.filter(child => child.tagName === "BUTTON") : children;
  }
  get firstElementChild() { return this.children[0]; }
  get childNodes() { return this.children; }
  reset() {
    const fields = this.id === "screens-label-form" ? ["screens-module","screens-page","screens-state"] : ["screens-device","screens-app-search","screens-app","screens-title"];
    for (const id of fields) if (elements.has(id)) elements.get(id).value = "";
  }
  showModal() { this.open = true; }
}
for (const match of html.matchAll(/<([a-z]+)[^>]*\bid="([^"]+)"[^>]*>/g)) elements.set(match[2], new El(match[1], match[2]));
elements.get("screens-create").append(new El("span"));
const gesture = new El("button"); gesture.dataset.screenAction = "back";
const swipe = new El("button"); swipe.dataset.screenSwipe = "up";
const document = {
  querySelectorAll(selector) {
    if (selector.includes("data-screen-action")) return [gesture,swipe,...all.filter(item => item.className === "screens-element")];
    return [];
  }
};
const $ = id => { assert(elements.has(id), "Missing DOM ID " + id); return elements.get(id); };
const node = (tag,className,text) => {const element=new El(tag);element.className=className||"";element.textContent=text||"";return element;};
const Option = function(text,value) {const element=new El("option");element.textContent=text;element.value=value;return element;};
const calls = [];
let pending = null;
let nextActionError = null;
const own = {id:"own",title:"My screens",serial:"fixture",package:"com.fixture",owner_id:"alice",status:"active",can_control:true,modules:[],pages:[],states:[],flows:[]};
const observation = {id:"o-123",status:"ok",actionable:true,clickables:[{index:7,text:"Library"}],screenshot_url:"/api/captures/own/files/screenshots/a.png"};
const other = {...own,id:"other",owner_id:"bob",can_control:false,observation:{...observation,screenshot_url:"/api/captures/own/files/screenshots/private.png"}};
async function api(path,options={}) {
  calls.push({path,options,body:options.body ? JSON.parse(options.body) : null});
  if (nextActionError && path.endsWith("/action")) { const error=nextActionError;nextActionError=null;throw error; }
  if (pending && path === pending.path) return new Promise(resolve => pending.resolve=resolve);
  if (path === "/api/capture/meta") return {available:true,message:"Fixture only"};
  if (path === "/api/captures" && !options.method) return {captures:[own,other]};
  if (path === "/api/capture/devices") return {devices:[{serial:"fixture",state:"device",model:"Test"}]};
  if (path.startsWith("/api/capture/apps?")) return {apps:[{package:"com.fixture"}]};
  if (path === "/api/captures" && options.method) return {capture:{...own}};
  if (path === "/api/captures/other") return {capture:{...other}};
  if (path === "/api/captures/own") return {capture:{...own}};
  if (path.endsWith("/launch") || path.endsWith("/action") || path.endsWith("/observe")) return {capture:{...own,observation}};
  if (path.endsWith("/label")) return {capture:{...own,observation,modules:[{id:"m",title:"Core"}],pages:[{id:"p",module_id:"m",title:"Library"}],states:[{id:"s",page_id:"p",title:"Empty",screenshot_url:observation.screenshot_url}]}};
  if (path.endsWith("/release")) return {capture:{...(path.includes("/other/")?other:own),status:"paused",observation}};
  throw Error("Unexpected request " + path);
}
const context = vm.createContext({window:{},document,$,node,Option,api,location:{origin:"http://127.0.0.1:8766"},URL,console,Date,Set,Map,Number,String,Boolean,Array,Object,
  currentUser:{id:"alice",role:"member"},authGeneration:1,confirm:()=>true,setAlert:(id,message)=>{$(id).textContent=message||"";$(id).hidden=!message;},dateText:()=>"Fixture time"});
vm.runInContext(fs.readFileSync(STATIC+"/screens.js","utf8"),context);
async function flush() { for(let i=0;i<4;i++) await new Promise(resolve=>setImmediate(resolve)); }
async function fire(element,event="click") {for(const fn of element.listeners[event]||[])await fn({preventDefault(){}});await flush();}
(async()=>{
  context.window.CollectorScreens.enterSession();
  assert.equal(calls.length,0,"Login must not inspect or operate a device");
  await fire($("nav-screens"));
  assert.deepEqual(calls.map(call=>call.path),["/api/capture/meta","/api/captures"]);
  context.window.CollectorScreens.openForPackage("com.fixture", "From store result");await flush();
  assert.equal(calls.length,2,"Store result shortcut must not inspect or operate a device");
  assert.equal($("screens-title").value,"From store result");
  await fire($("screens-devices-refresh"));
  $("screens-device").value="fixture"; await fire($("screens-device"),"change");
  assert.equal($("screens-app").value,"com.fixture","Store package is only matched after explicit device choice");
  $("screens-app").value="com.fixture"; await fire($("screens-app"),"change");
  assert.equal($("screens-create").disabled,false);
  await fire($("screens-create-form"),"submit");
  assert.equal($("screens-image").src,"");
  assert(!calls.some(call=>call.path.endsWith("/launch")),"Create must not launch App");
  await fire($("screens-launch"));
  assert($("screens-image").src.endsWith("/api/captures/own/files/screenshots/a.png"));
  const clickable=$("screens-elements").children[0]; await fire(clickable);
  const tap=calls.filter(call=>call.path.endsWith("/action")).at(-1);
  assert.deepEqual(tap.body,{observation_id:"o-123",action:"tap",index:7});
  assert.equal(tap.options.timeoutMs,120000);
  nextActionError=new Error("Device operation uncertain");
  await fire($("screens-elements").children[0]);
  assert.equal(gesture.disabled,true,"Unconfirmed operation must invalidate old controls");
  assert.equal($("screens-label").disabled,true,"Unconfirmed current page must not be labelled");
  await fire($("screens-observe"));
  await fire(gesture); assert.equal(calls.at(-2).body.action,"back");
  $("screens-module").value="Core"; $("screens-page").value="Library"; $("screens-state").value="Empty";
  await fire($("screens-label-form"),"submit");
  assert(calls.some(call=>call.path.endsWith("/label")&&call.body.observation_id==="o-123"));
  assert.equal($("screens-saved").children.length,1);
  assert.equal($("screens-export").disabled,false);
  await fire($("screens-session-actions").querySelectorAll("button")[0]);
  assert.equal(gesture.disabled,true,"Paused capture must not operate device");
  await fire($("screens-sessions").children[1]);
  assert.equal($("screens-readonly").hidden,false);
  assert.equal($("screens-launch").disabled,true);
  assert.equal($("screens-session-actions").querySelectorAll("button").length,0);
  assert.equal($("screens-image").src,"","Other-record file URL must not be rendered");
  const before=calls.length; await fire($("screens-launch"));assert.equal(calls.length,before,"Readonly controls must not send commands");
  context.currentUser={id:"alice",role:"admin"};
  await fire($("screens-sessions").children[1]);
  assert.equal($("screens-session-actions").querySelectorAll("button").length,1,"Admin can only release another owner's lease");
  await fire($("screens-session-actions").querySelectorAll("button")[0]);
  assert(calls.some(call=>call.path==="/api/captures/other/release"));
  assert.equal($("screens-launch").disabled,true);
  pending={path:"/api/captures/own"};const opening=fire($("screens-sessions").children[0]);await flush();
  context.currentUser=null;context.authGeneration++;context.window.CollectorScreens.reset();
  pending.resolve({capture:{...own,observation}});await opening;
  assert.equal($("screens-image").src,"");
  assert.equal($("screens-current").hidden,true);
  assert.equal($("screens-sessions").children.length,0);
  assert.equal($("screens-module").value,"");
  assert.equal($("screens-app-search").value,"");
  console.log("capture frontend runtime checks passed");
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    script = "const STATIC = " + json.dumps(str(STATIC)) + ";\n" + harness
    result = subprocess.run([shutil.which("node"), "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "runtime checks passed" in result.stdout
