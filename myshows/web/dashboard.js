"use strict";

const snapshot = JSON.parse(document.getElementById("watchlist-data").textContent);
const $ = id => document.getElementById(id);
const dateFormat = new Intl.DateTimeFormat("en-GB", {day:"numeric",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit"});
const dayFormat = new Intl.DateTimeFormat("en-GB", {day:"numeric",month:"short",year:"numeric",timeZone:"UTC"});
const monthFormat = new Intl.DateTimeFormat("en-GB", {month:"long",year:"numeric",timeZone:"UTC"});
const kindLabels = {release:"RELEASE ANNOUNCED",production:"PRODUCTION UPDATE",renewal:"RENEWED",outcome:"SERIES OUTCOME",unknown:"STATUS UNKNOWN"};
let activeFilter = "all";

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = String(text);
  return node;
}
function date(value) {
  const parsed = value && new Date(value);
  return parsed && !Number.isNaN(parsed.getTime()) ? dateFormat.format(parsed) : "Unknown";
}
function day(value) { return value ? dayFormat.format(new Date(value + "T12:00:00Z")) : "Not supplied"; }
function old(value, days=1) { return !!value && Date.now()-new Date(value).getTime()>days*86400000; }
function reference(value) { return value ? `S${String(value.season).padStart(2,"0")}E${String(value.episode).padStart(2,"0")}` : "Unknown"; }
function link(text, href, className="") {
  const node = element("a",className,text);
  node.href=href;node.target="_blank";node.rel="noreferrer";
  return node;
}
function timeNode(value) {
  const node=element("time","",date(value));
  if(value) node.dateTime=value;
  return node;
}
function releaseEnd(release) {
  if(!release) return null;
  if(release.precision==="day") return release.value;
  if(release.precision==="month") {
    const [year,month]=release.value.split("-").map(Number);
    return new Date(Date.UTC(year,month,0)).toISOString().slice(0,10);
  }
  return release.precision==="year" ? release.value+"-12-31" : null;
}
function passed(release) {
  const end=releaseEnd(release);
  return !!end && end<new Date().toISOString().slice(0,10);
}
function releaseText(release) {
  if(release.precision==="day") return day(release.value);
  if(release.precision==="month") return monthFormat.format(new Date(release.value+"-01T12:00:00Z"));
  return release.value;
}
function facts(show) { return show.status?.facts || []; }

function statusBlock(show,body) {
  const lead=show.status?.lead;
  if(!lead) {
    body.append(element("span","status-label","WHAT'S NEXT"),element("p","status-headline","Status unknown."),element("p","status-region","No sourced update has been added for this show yet."));
    return;
  }
  const overdue=lead.release && passed(lead.release);
  body.append(element("span","status-label",overdue ? "LAST ANNOUNCED RELEASE" : "WHAT'S NEXT"),element("p","status-headline",lead.headline));
  if(lead.release) body.append(element("p","status-region",`${releaseText(lead.release)} · ${lead.release.region}`));
  const evidence=element("div","status-evidence");
  evidence.append(element("span",`evidence-label evidence-${lead.confidence}`,lead.confidence.toUpperCase()),link(lead.sources[0].name+" ↗",lead.sources[0].url));
  const published=lead.sources[0].published_on;
  if(published) evidence.append(element("span","",`Published ${day(published)}`));
  evidence.append(element("span","",`Checked ${day(lead.checked_on)}`));
  body.append(evidence);
  const secondary=facts(show).filter(f=>f.id!==lead.id && (f.kind==="renewal"||f.kind==="outcome"));
  for(const fact of secondary) body.append(element("p","status-secondary",fact.headline));
  if(overdue) body.append(element("p","status-warning","The announced date/window has passed. A new status check is needed; availability has not been inferred."));
  else if(old(lead.checked_on,30)) body.append(element("p","status-warning","Status evidence was last checked over 30 days ago. Needs another check."));
}

function showRow(show,index) {
  const lead=show.status?.lead;
  const kind=lead?.kind||"unknown";
  const item=element("li",`show show-${kind}`);
  const article=element("article");
  const banner=element("div","show-banner");
  banner.append(element("span","",`${String(index+1).padStart(2,"0")} / ${kindLabels[kind]}`),element("span","","↗"));
  banner.lastChild.setAttribute("aria-hidden","true");
  const body=element("div","show-body");
  const title=element("div","show-title");
  const heading=element("h3");heading.append(link(show.title,show.url));
  title.append(heading,element("span","show-year",show.year||"Year unknown"));
  body.append(title);statusBlock(show,body);
  const strip=element("div","progress-strip");
  const progress=element("div");progress.append(element("span","cell-label","YOUR WATCHED PROGRESS"));
  const p=show.progress;
  if(p) {
    const top=element("div","progress-top");top.append(element("strong","",`${p.watched} / ${p.aired}`),element("span","","aired episodes"));
    const bar=element("div","progress-bar");bar.setAttribute("aria-hidden","true");
    const fill=element("span");fill.style.width=`${p.aired ? Math.round(p.watched/p.aired*100) : 0}%`;bar.append(fill);
    const caption=p.recent ? `Last watched ${reference(p.recent)}` : p.watched===0 ? "Not started" : "Last viewing unknown";
    progress.append(top,bar,element("p","progress-caption",caption));
  } else progress.append(element("span","progress-caption","Progress unknown"));
  const unwatched=element("div","unwatched-cell");unwatched.append(element("span","cell-label","TO WATCH"));
  const kindPill=!p||!p.aired ? "unknown" : p.aired_unwatched ? "unwatched" : "caught-up";
  const pillText=!p ? "Unknown" : !p.aired ? "None aired yet" : p.aired_unwatched ? `${p.aired_unwatched} ${p.aired_unwatched===1 ? "episode" : "episodes"}` : "✓ Caught up";
  unwatched.append(element("span",`pill pill-${kindPill}`,pillText));strip.append(progress,unwatched);body.append(strip);
  const checked=element("div","progress-freshness");checked.append(element("span","","PROGRESS CHECKED"),timeNode(show.checked_at));
  if(show.refresh_failed) checked.append(element("span","warning-tag","Refresh failed — retained data"));
  else if(old(show.checked_at)) checked.append(element("span","warning-tag","Older snapshot"));
  body.append(checked);
  const details=element("details","show-details");
  details.append(element("summary","",`SOURCES & OTHER UPDATES (${facts(show).length})`));
  const content=element("div","details-content");
  for(const fact of facts(show)) {
    const block=element("section","fact");
    block.append(element("h4","",fact.headline),element("p","",fact.detail));
    if(fact.release) block.append(element("p","",`Announced: ${releaseText(fact.release)} · ${fact.release.region}`));
    block.append(element("p","fact-meta",`${fact.confidence.toUpperCase()} · ${kindLabels[fact.kind]} · Checked ${day(fact.checked_on)}`));
    for(const source of fact.sources) block.append(link(`${source.name} ↗${source.published_on ? " · "+day(source.published_on) : ""}`,source.url,"fact-source"));
    if(old(fact.checked_on,30)) block.append(element("p","details-warning","This evidence needs another check."));
    content.append(block);
  }
  const history=element("div","details-progress");
  if(p) {
    history.append(element("p","",`Most recently watched: ${reference(p.recent)}`),element("p","",`Furthest watched: ${reference(p.furthest)}`));
    if(p.recent?.watched_at) history.append(element("p","",`Viewed: ${date(p.recent.watched_at)}`));
    if(p.rewatch_reset) history.append(element("p","details-warning","A rewatch reset exists; counts use Trakt totals without a local reset."));
  }
  history.append(element("p","",`Progress last checked: ${date(show.checked_at)}`),link("Viewing progress from Trakt ↗",show.url));
  content.append(history);details.append(content);article.append(banner,body,details);item.append(article);return item;
}

function updateSummary() {
  const known=snapshot.shows.filter(s=>s.progress!==null);
  const validTotals=known.length || (snapshot.list_checked_at&&!snapshot.shows.length);
  $("total-shows").textContent=snapshot.list_checked_at ? String(snapshot.shows.length).padStart(2,"0") : "—";
  $("total-unwatched").textContent=validTotals ? known.reduce((sum,s)=>sum+s.progress.aired_unwatched,0) : "—";
  $("caught-up").textContent=validTotals ? known.filter(s=>s.progress.aired>0&&!s.progress.aired_unwatched).length : "—";
  $("announced-shows").textContent=snapshot.shows.filter(s=>facts(s).some(f=>f.kind==="release"&&!passed(f.release))).length;
  if(known.length!==snapshot.shows.length) $("unwatched-caption").textContent=`Across ${known.length} shows with known progress; UK availability may differ.`;
  $("list-count").textContent=snapshot.list_checked_at ? snapshot.shows.length : "?";
  $("list-checked").textContent=date(snapshot.list_checked_at);
  if(snapshot.list_checked_at) $("list-checked").dateTime=snapshot.list_checked_at;
  const messages=[];
  if(!snapshot.list_checked_at) messages.push("The watchlist has not been retrieved successfully yet.");
  else if(snapshot.list_refresh_failed) messages.push("The watchlist refresh failed. Showing the last successful list.");
  else if(old(snapshot.list_checked_at)) messages.push("Watched-list data is more than 24 hours old. This does not change the separately dated status evidence.");
  const failed=snapshot.shows.filter(s=>s.refresh_failed).length;
  if(failed) messages.push(`Progress refresh failed for ${failed} ${failed===1 ? "show" : "shows"}; earlier values are retained where available.`);
  $("data-notice").hidden=!messages.length;$("data-notice").textContent=messages.join(" ");
}
function upcoming(show) {
  return facts(show).filter(f=>f.release&&!passed(f.release)).map(f=>releaseEnd(f.release)).filter(Boolean).sort()[0]||"9999-12-31";
}
function render() {
  const query=$("search").value.trim().toLocaleLowerCase("en-GB");
  let shows=snapshot.shows.filter(s=>s.title.toLocaleLowerCase("en-GB").includes(query));
  if(activeFilter==="unwatched") shows=shows.filter(s=>s.progress&&s.progress.aired_unwatched>0);
  if(activeFilter==="caught-up") shows=shows.filter(s=>s.progress&&s.progress.aired>0&&!s.progress.aired_unwatched);
  const status=$("status-filter").value;
  if(status==="unknown") shows=shows.filter(s=>!s.status?.lead);
  else if(status!=="all") shows=shows.filter(s=>facts(s).some(f=>f.kind===status));
  shows.sort((a,b)=> {
    if($("sort").value==="release") {const order=upcoming(a).localeCompare(upcoming(b));if(order)return order;}
    if($("sort").value==="unwatched") {const order=(b.progress?.aired_unwatched??-1)-(a.progress?.aired_unwatched??-1);if(order)return order;}
    return a.title.localeCompare(b.title,"en-GB");
  });
  $("shows").replaceChildren(...shows.map(showRow));
  $("empty-state").hidden=shows.length>0;
  const empty=!snapshot.shows.length;
  $("clear-filters").hidden=empty;
  $("empty-title").textContent=empty ? snapshot.list_checked_at ? "A NEW STORY STARTS HERE." : "WATCHLIST UNKNOWN." : "NO MATCHES. TRY AGAIN.";
  $("empty-copy").textContent=empty ? snapshot.list_checked_at ? "Your saved Trakt list contains no shows yet." : "There is no successfully saved watchlist to display." : "Try another title or a different filter.";
  $("results-count").textContent=`${shows.length} of ${snapshot.shows.length} shows displayed`;
  document.querySelectorAll("[data-filter]").forEach(button=>button.setAttribute("aria-pressed",String(button.dataset.filter===activeFilter)));
}
document.querySelector(".toolbar").addEventListener("submit",event=>event.preventDefault());
document.querySelectorAll("[data-filter]").forEach(button=>button.addEventListener("click",()=>{activeFilter=button.dataset.filter;render();}));
$("search").addEventListener("input",render);$("sort").addEventListener("change",render);$("status-filter").addEventListener("change",render);
$("clear-filters").addEventListener("click",()=>{activeFilter="all";$("search").value="";$("status-filter").value="all";render();$("search").focus();});
updateSummary();render();
