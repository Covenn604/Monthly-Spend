const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
function fixture(){
 const elements={};
 const $=id=>elements[id]??=( {value:'',checked:false,hidden:false,disabled:false,innerHTML:''});
 const state={accounts:Array.from({length:5},(_,i)=>({id:i+1,name:`Account ${i+1}`,default_profile:`Format ${i+1}`})),profiles:Array.from({length:5},(_,i)=>({name:`Format ${i+1}`,mapping:{delimiter:i%2?';':',',skip_lines:i,date_format:i%2?'compact':'dmy_short_month',mode:i%2?'split':'signed',invert:i%2===0,decimal_comma:i%2===1,date:'0',payee:'1',amount:'2',debit:'2',credit:'3'}}))};
 const requests=[];
 const context=vm.createContext({$,state,esc:String,headerRequest:0,previewRequest:0,importProfileAccount:null,importPreview:{},csvText:'',csvHeaders:[],api:async(path,method,data)=>{requests.push(data);return {headers:['Date','Description','Debit','Credit']};}});
 const src=fs.readFileSync('static/app.js','utf8');
 vm.runInContext(src.slice(src.indexOf('function mapping()'),src.indexOf('function renderPreview()')),context);
 return {context,$,state,requests};
}
test('five account defaults before and after upload, reload, and manual override',async()=>{
 for(const uploaded of [false,true]){
  const {context:c,$,state,requests}=fixture();
  c.csvText=uploaded?'synthetic statement':'';
  for(const id of [1,2,3,4,5,1]){
   $('#import-account').value=String(id);c.importPreview={};
   await c.selectAccountProfile();
   const m=state.profiles[id-1].mapping;
   assert.equal($('#profile').value,`Format ${id}`);
   assert.equal($('#delimiter').value,m.delimiter);
   assert.equal($('#date-format').value,m.date_format);
   assert.equal($('#amount-mode').value,m.mode);
   assert.equal($('#invert').checked,m.invert);
   assert.equal($('#decimal-comma').checked,m.decimal_comma);
   assert.equal(c.importPreview,null);
   if(uploaded)assert.equal(requests.at(-1).skip_lines,m.skip_lines);
  }
  $('#profile').value='Format 5';await c.selectProfile();
  assert.equal(state.accounts[0].default_profile,'Format 1');
  await c.selectAccountProfile();assert.equal($('#profile').value,'Format 1');
  state.accounts.push({id:6,name:'No default'});
  $('#import-account').value='6';await c.selectAccountProfile();
  assert.equal($('#profile').value,'');assert.equal($('#invert').checked,false);
  assert.equal($('#decimal-comma').checked,false);assert.equal($('#delimiter').value,',');
  assert.equal($('#date-format').value,'iso');assert.equal($('#skip-lines').value,0);
 }
});
test('file loaded after selection applies stored columns; stale header responses ignored',async()=>{
 const {context:c,$}=fixture();
 $('#import-account').value='2';await c.selectAccountProfile();
 c.csvText='synthetic statement';await c.loadHeaders();
 assert.equal($('#map-credit').value,'3');
 let resolve;
 c.api=()=>new Promise(r=>{resolve=r;});
 const pending=c.loadHeaders();
 c.csvText='';$('#import-account').value='1';await c.selectAccountProfile();
 resolve({headers:['Wrong']});await pending;
 assert.equal($('#profile').value,'Format 1');assert.equal($('#invert').checked,true);
 assert.notDeepEqual(c.csvHeaders,['Wrong']);
});
test('account switch discards a pending transaction preview',async()=>{
 const {context:c,$}=fixture();
 c.task=fn=>fn();c.renderPreview=()=>{throw Error('Stale preview was rendered');};
 const src=fs.readFileSync('static/app.js','utf8');
 vm.runInContext(src.slice(src.indexOf("$('#preview-csv').onclick"),src.indexOf("$('#commit-csv').onclick")),c);
 let resolve;c.api=()=>new Promise(r=>{resolve=r;});
 const pending=$('#preview-csv').onclick({currentTarget:{}});
 $('#import-account').value='2';await c.selectAccountProfile();
 resolve({token:'old',rows:[]});await pending;
 assert.equal(c.importPreview,null);
});
