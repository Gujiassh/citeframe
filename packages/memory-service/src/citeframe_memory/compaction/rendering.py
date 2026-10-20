"""Authenticated interval provenance and chronological checkpoint rendering."""
from dataclasses import asdict
from sqlalchemy import select
from citeframe_contracts.memory import GenerationMessage
from citeframe_persistence.models import MemoryCall, TaskMemorySnapshot
from .guards import canonical, digest, lock_one
from .policy import CompactionError, CompactionPolicy
from .summary import validate_summary
from .units import ContextUnit


def validate_profile(profile):
    fields={"schemaVersion","provider","protocol","model","configFingerprint","contextWindowTokens",
            "maxOutputTokens","inputCeiling","safetyMargin","counter","watermarks"}
    if not isinstance(profile,dict) or set(profile)!=fields or profile["schemaVersion"]!="compaction-dispatch-profile-v1":
        raise CompactionError("dispatch_profile_required")
    if any(not isinstance(profile[k],str) or not profile[k] for k in ("provider","protocol","model","configFingerprint")):
        raise CompactionError("invalid_dispatch_profile")
    if any(type(profile[k]) is not int or profile[k]<=0 for k in ("contextWindowTokens","maxOutputTokens","inputCeiling")) or type(profile["safetyMargin"]) is not int or profile["safetyMargin"]<0:
        raise CompactionError("invalid_dispatch_profile")
    counter=profile["counter"]
    if (not isinstance(counter,dict) or set(counter)!={"counter_id","counter_version","mode","config_fingerprint"}
            or any(not isinstance(v,str) or not v for v in counter.values()) or counter["mode"] not in ("exact","estimated")
            or counter["config_fingerprint"]!=profile["configFingerprint"]):
        raise CompactionError("invalid_dispatch_profile")
    try:
        policy=CompactionPolicy(**profile["watermarks"])
    except (TypeError,ValueError):raise CompactionError("invalid_dispatch_profile") from None
    if asdict(policy)!=profile["watermarks"]:raise CompactionError("invalid_dispatch_profile")
    return profile


def input_manifest(captured,policy,profile,plan=None,descriptor=None):
    validate_profile(profile)
    result={"schemaVersion":"compaction-input-v2","capture":asdict(captured),"policy":policy,"dispatchProfile":profile}
    if plan is not None or descriptor is not None:
        validate_plan(plan,[asdict(u) for u in captured.units])
        result.update(compactionPlan=plan,summaryInput=descriptor)
    if len(canonical(result).encode())>131072:raise CompactionError("context_too_large")
    return result


def match_input(row,captured,policy,profile,plan=None,descriptor=None):
    expected=input_manifest(captured,policy,profile,plan,descriptor)
    if canonical(row.input_manifest)!=canonical(expected):raise CompactionError("dispatch_binding_changed")


def validate_plan(plan,units):
    if (not isinstance(plan,dict) or set(plan)!={"schemaVersion","intervalStart","intervalEnd","protectedUnitKeys"}
            or plan["schemaVersion"]!="compaction-plan-v1"):
        raise CompactionError("checkpoint_rendering_metadata_required")
    a,b=plan["intervalStart"],plan["intervalEnd"];keys=[u["key"] for u in units];protected=plan["protectedUnitKeys"]
    if (type(a) is not int or type(b) is not int or not 0<=a<b<=len(keys) or len(keys)!=len(set(keys))
            or not isinstance(protected,list) or any(not isinstance(k,str) for k in protected)
            or protected!=[k for k in keys if k in protected] or any(k in protected for k in keys[a:b])):
        raise CompactionError("invalid_compaction_plan")
    return keys[a:b]


def _support(summary):
    from .summary import ARRAYS
    atoms=[a for name in ARRAYS for a in summary[name]]
    atoms += [side for conflict in summary["conflicts"] for side in (conflict["sideA"],conflict["sideB"])]
    return {canonical(ref) for atom in atoms for ref in atom["sourceRefs"]}


def validate_result(db,row,summary,*,saved=False):
    from citeframe_contracts.compaction import CoverageUnit,SourceReference
    manifest=row.input_manifest
    if row.request_object_key is None:raise CompactionError("summary_request_archive_required")
    if manifest.get("schemaVersion")!="compaction-input-v2":raise CompactionError("checkpoint_rendering_metadata_required")
    validate_profile(manifest.get("dispatchProfile"))
    originals=manifest["capture"]["units"];plan=manifest.get("compactionPlan");descriptor=manifest.get("summaryInput")
    interval=validate_plan(plan,originals);mapping={u["key"]:u for u in originals}
    if not isinstance(descriptor,dict) or descriptor.get("schemaVersion")!="compaction-summary-input-v1":
        raise CompactionError("invalid_summary_input")
    child_support=None
    if row.purpose=="compact_chunk":
        if set(descriptor)!={"schemaVersion","kind","originalUnitKeys"} or descriptor["kind"]!="original_units":raise CompactionError("invalid_summary_input")
        keys=descriptor["originalUnitKeys"]
        if (not isinstance(keys,list) or not keys or any(not isinstance(k,str) or k not in interval for k in keys)
                or keys!=interval[interval.index(keys[0]):interval.index(keys[0])+len(keys)]):raise CompactionError("invalid_summary_input")
    elif row.purpose=="compact_merge":
        if set(descriptor)!={"schemaVersion","kind","children"} or descriptor["kind"]!="child_results":raise CompactionError("invalid_summary_input")
        children=descriptor["children"]
        if not isinstance(children,list) or not 1<=len(children)<=manifest["dispatchProfile"]["watermarks"]["max_chunk_calls"]:raise CompactionError("invalid_summary_children")
        keys=[];seen=set();child_support=set()
        for entry in children:
            if not isinstance(entry,dict) or set(entry)!={"callId","resultSha256","inputManifestSha256"} or entry["callId"] in seen:raise CompactionError("invalid_summary_children")
            seen.add(entry["callId"]);child=lock_one(db,MemoryCall,entry["callId"])
            if (child is None or child.purpose!="compact_chunk" or child.state!="succeeded" or child.result_state!="valid"
                    or child.workspace_id!=row.workspace_id or child.actor_user_id!=row.actor_user_id
                    or child.chat_execution_id!=row.chat_execution_id or child.research_attempt_id!=row.research_attempt_id
                    or child.result_sha256!=entry["resultSha256"] or digest(child.input_manifest)!=entry["inputManifestSha256"]
                    or any(canonical(child.input_manifest.get(k))!=canonical(manifest.get(k)) for k in ("capture","policy","dispatchProfile","compactionPlan"))):raise CompactionError("invalid_summary_children")
            value=child.result_manifest.get("summary")
            validate_result(db,child,value,saved=True)
            keys.extend(child.input_manifest["summaryInput"]["originalUnitKeys"]);child_support|=_support(value)
        if (len(keys)!=len(set(keys)) or any(k not in interval for k in keys)
                or keys!=[k for k in interval if k in keys]):raise CompactionError("invalid_summary_children")
    else:raise CompactionError("invalid_summary_input")
    units=tuple(CoverageUnit(u["key"],SourceReference(**u["source"]) if u["source"] else None,
                             u["tool_group_id"],u["parent_message_id"]) for u in (mapping[k] for k in keys))
    validate_summary(summary,units)
    if child_support is not None and not _support(summary).issubset(child_support):raise CompactionError("invalid_summary_source")
    result={"schemaVersion":"compaction-result-v2","summary":summary,"compactionPlan":plan,"summaryInput":descriptor,"finalEligible":keys==interval}
    if saved and (row.result_sha256!=digest(summary) or canonical(row.result_manifest)!=canonical(result)):
        raise CompactionError("summary_result_provenance_changed")
    return result


def append_interval(intervals,plan,summary):
    a,b=plan["intervalStart"],plan["intervalEnd"]
    remaining=[]
    for old in intervals:
        x,y=old[0],old[1]
        if b<=x or a>=y:remaining.append(old)
        elif not (a<=x and b>=y):raise CompactionError("checkpoint_partial_overlap")
    return tuple(sorted(remaining+[(a,b,summary)],key=lambda entry:entry[0]))


def advance_intervals(intervals,protected,frontier,plan,summary,units):
    validate_plan(plan,units)
    next_protected=frozenset(plan["protectedUnitKeys"])
    if not protected.issubset(next_protected) or plan["intervalEnd"]<=frontier:
        raise CompactionError("checkpoint_plan_regression")
    next_intervals=append_interval(intervals,plan,summary)
    if any(unit["key"] in next_protected for a,b,_ in next_intervals for unit in units[a:b]):
        raise CompactionError("checkpoint_protected_anchor_hidden")
    return next_intervals,next_protected,plan["intervalEnd"]


def render(units,intervals):
    result=[];cursor=0
    for a,b,summary in intervals:
        result.extend(units[cursor:a])
        if summary is not None:
            result.append(ContextUnit("checkpoint:"+str(a)+":"+str(b),"messages",(GenerationMessage("assistant",canonical({"taskMemoryData":summary})),)))
        cursor=b
    result.extend(units[cursor:]);return tuple(result)


def load_intervals(db,captured,policy,proposed=None):
    chain=[];key=captured.checkpoint_id;seen=set();budget=0
    while key:
        if key in seen or len(chain)>=policy["maxEpisodes"]:raise CompactionError("checkpoint_chain_limit")
        seen.add(key);snapshot=lock_one(db,TaskMemorySnapshot,key)
        if snapshot is None or snapshot.status!="committed" or snapshot.workspace_id!=captured.owner.workspace_id or snapshot.owner_user_id!=captured.owner.actor_user_id:
            raise CompactionError("checkpoint_unavailable")
        call=lock_one(db,MemoryCall,snapshot.generation_call_id) if snapshot.generation_call_id else None
        if (call is None or (call.chat_execution_id or call.research_attempt_id)!=captured.owner.owner_id
                or call.state!="succeeded" or call.result_state!="valid"):raise CompactionError("checkpoint_rendering_metadata_required")
        result=validate_result(db,call,snapshot.summary,saved=True)
        if not result["finalEligible"]:raise CompactionError("summary_not_final")
        original=call.input_manifest["capture"];now=asdict(captured)
        end=result["compactionPlan"]["intervalEnd"]
        if (canonical(original["units"][:end])!=canonical(now["units"][:end])
                or original["checkpoint_id"]!=snapshot.parent_snapshot_id or original["context_version"]+1!=snapshot.context_version
                or original["checkpoint_version"]+1!=snapshot.version):raise CompactionError("checkpoint_capture_changed")
        budget+=len(canonical(call.input_manifest).encode())+len(canonical(result).encode())
        if budget>1048576:raise CompactionError("checkpoint_chain_limit")
        chain.append(result);key=snapshot.parent_snapshot_id
    if proposed is not None:
        manifest,result=proposed
        budget+=len(canonical(manifest).encode())+len(canonical(result).encode())
        if len(chain)+1>policy["maxEpisodes"] or budget>1048576:
            raise CompactionError("checkpoint_chain_limit")
    intervals=();protected=set();frontier=0
    for result in reversed(chain):
        plan=result["compactionPlan"]
        intervals,protected,frontier=advance_intervals(intervals,protected,frontier,plan,result["summary"],asdict(captured)["units"])
    return intervals,frozenset(protected),frontier


def validate_physical_summary(db,row,request):
    """The archived request must contain the descriptor's exact authenticated data."""
    import json
    manifest=row.input_manifest;descriptor=manifest.get("summaryInput")
    if row.purpose not in ("compact_chunk","compact_merge"):return
    if request.tools or not request.messages or request.messages[0].role!="system":raise CompactionError("summary_payload_changed")
    try:
        if row.purpose=="compact_chunk":
            keys=descriptor["originalUnitKeys"];originals={u["key"]:u for u in manifest["capture"]["units"]}
            if len(request.messages)!=len(keys)+1:raise ValueError()
            for key,message in zip(keys,request.messages[1:]):
                envelope=json.loads(message.content)
                if set(envelope)!={"sourceUnit"}:raise ValueError()
                outer=envelope["sourceUnit"]
                if (message.role!="user" or message.tool_calls or message.tool_call_id is not None
                        or set(outer)!={"key","kind","messages","resultStates"} or outer["kind"]!="messages" or outer["resultStates"]
                        or outer["key"]!=key or len(outer["messages"])!=1):raise ValueError()
                nested=outer["messages"][0]
                if set(nested)!={"role","content","tool_calls","tool_call_id"} or nested["role"]!="user" or nested["tool_calls"] or nested["tool_call_id"] is not None:raise ValueError()
                payload=json.loads(outer["messages"][0]["content"])
                if set(payload)!={"original","messages","resultStates"} or payload["original"]!=originals[key]:raise ValueError()
                original=originals[key]
                if original["source"]:
                    from citeframe_persistence.models import MemorySource
                    source=lock_one(db,MemorySource,original["source"]["source_id"])
                    messages=payload["messages"]
                    if (len(messages)!=1 or set(messages[0])!={"role","content","tool_calls","tool_call_id"}
                            or messages[0]["role"]!=source.native_version.get("role","user")
                            or messages[0]["tool_calls"] or messages[0]["tool_call_id"] is not None
                            or __import__("hashlib").sha256(messages[0]["content"].encode()).hexdigest()!=source.content_sha256
                            or payload["resultStates"]):raise ValueError()
                else:
                    group=lock_one(db,MemoryCall,original["tool_group_id"])
                    if digest({"messages":payload["messages"],"states":payload["resultStates"]})!=group.result_sha256:raise ValueError()
        else:
            if (len(request.messages)!=2 or request.messages[1].role!="user"
                    or request.messages[1].tool_calls or request.messages[1].tool_call_id is not None):raise ValueError()
            values=[]
            for entry in descriptor["children"]:
                child=lock_one(db,MemoryCall,entry["callId"])
                if child.result_sha256!=entry["resultSha256"] or digest(child.input_manifest)!=entry["inputManifestSha256"]:raise ValueError()
                values.append(child.result_manifest["summary"])
            if json.loads(request.messages[1].content)!={"chunkSummaries":values}:raise ValueError()
    except (KeyError,TypeError,ValueError,AttributeError):raise CompactionError("summary_payload_changed") from None
