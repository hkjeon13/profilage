const preview = document.querySelector("#preview");
const status = document.querySelector("#status");
let captured;
document.querySelector("#capture").addEventListener("click", async () => {
  const [tab] = await chrome.tabs.query({active:true,currentWindow:true});
  const [{result}] = await chrome.scripting.executeScript({target:{tabId:tab.id},func:() => ({url:location.href,title:document.title,lang:document.documentElement.lang,text:String(getSelection()?.toString()||"").trim()})});
  if (!result.text || result.text.length < 80) { status.textContent="80자 이상의 본문을 직접 선택해 주세요."; return; }
  captured=result; preview.value=result.text.slice(0,4000); document.querySelector("#send").disabled=false; status.textContent="선택 내용을 확인한 뒤 분석 요청을 누르세요.";
});
document.querySelector("#send").addEventListener("click", async () => {
  const intentId=document.querySelector("#intent").value.trim(), token=document.querySelector("#token").value.trim();
  if (!captured || !intentId || !token) { status.textContent="Intent와 token을 입력해 주세요."; return; }
  const response=await fetch("https://profile.fin-ally.net/api/person/page-analysis/captures",{method:"POST",headers:{"Content-Type":"application/json","Authorization":`Capture ${token}`,"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify({intent_id:intentId,page:{url:captured.url,title:captured.title,lang:captured.lang,captured_at:new Date().toISOString()},capture_mode:"selection",blocks:[{client_block_id:"selection-1",kind:"main_text",text:captured.text.slice(0,4000)}],content_hash:null,user_reviewed:true})});
  const payload=await response.json().catch(()=>({})); status.textContent=response.ok?`분석 작업이 생성되었습니다: ${payload.job_id}`:(payload.detail||"요청에 실패했습니다.");
});
