"""M30 · Private title-review rules, receipts, evidence and review reports."""

from copy import deepcopy
from datetime import date
import hashlib
import json

import streamlit as st

from utils import title_review as review
from utils import title_review_sync as private_sync
from utils.ui_theme import render_home_link


def persist(document):
    st.session_state["m30_draft"] = document
    result = private_sync.save_document(review.CASES_PATH, document, st.session_state["m30_cases_sha"], secrets=st.secrets)
    if not result["ok"]:
        st.session_state["m30_error"] = result["message"]
        st.rerun()
    st.session_state["m30_cases"] = result["document"]
    st.session_state["m30_cases_sha"] = result["sha"]
    st.session_state.pop("m30_draft", None)
    st.session_state["m30_flash"] = "已保存，并核对云端内容。"
    st.rerun()


def choice(label, options, current, key):
    return st.selectbox(label, options, index=options.index(current), key=key)


st.set_page_config(page_title="M30·职称评审", page_icon="📋", layout="wide")
render_home_link()
st.markdown("### 📋 M30·职称评审")

if "m30_rules" not in st.session_state or "m30_cases" not in st.session_state:
    with st.spinner("正在读取规则和收件记录…"):
        rules_result = private_sync.load_document(review.RULES_PATH, secrets=st.secrets)
        cases_result = private_sync.load_document(review.CASES_PATH, secrets=st.secrets)
    if not rules_result["ok"] or not cases_result["ok"]:
        st.error("私有评审资料尚未读到。请检查同步配置后重试。")
        if st.button("重试读取", key="m30_retry"):
            st.rerun()
        st.stop()
    if rules_result["document"] is None:
        st.info("尚未导入已确认的规则清单，请先由材料整理人员初始化规则。")
        st.stop()
    st.session_state["m30_rules"] = rules_result["document"]
    st.session_state["m30_cases"] = cases_result["document"] or review.empty_cases(rules_result["document"]["year"])
    st.session_state["m30_cases_sha"] = cases_result["sha"]

rulebook = st.session_state["m30_rules"]
document = st.session_state["m30_cases"]
st.caption(f"{rulebook['year']}年度 · 规则版本 {rulebook['version']} · 收件、逐项核验与学院复核分别记录。")
if st.session_state.get("m30_flash"):
    st.success(st.session_state.pop("m30_flash"))
if st.session_state.get("m30_error"):
    st.error(st.session_state.pop("m30_error"))
has_draft = "m30_draft" in st.session_state
if has_draft:
    st.warning("有一次未确认保存的草稿，请先下载备份，再刷新合并。")
    st.download_button("下载未保存草稿", json.dumps(st.session_state["m30_draft"], ensure_ascii=False, indent=2),
                       "职称评审_未保存草稿.json", "application/json", key="m30_draft_download")
    may_refresh = st.checkbox("我已保留草稿，允许重新读取云端", key="m30_allow_refresh")
else:
    may_refresh = True
if st.button("刷新云端记录", disabled=not may_refresh, key="m30_refresh"):
    # Only explicit refresh discards the editable snapshot; failed saves keep it.
    for key in list(st.session_state):
        if key.startswith("m30_"):
            del st.session_state[key]
    st.rerun()

rules_tab, receipt_tab, review_tab, summary_tab = st.tabs(["规则与附件", "收件台账", "逐人初审", "问题与汇总"])

with rules_tab:
    st.markdown("#### 本轮口径")
    st.dataframe([{"编号": d["id"], "状态": d["status"], "处理口径": d["text"]}
                  for d in rulebook["decisions"] if d["status"] != "个案再询问"], hide_index=True, width="stretch")
    st.caption("其他疑点仅在实际材料涉及并影响判断时询问，不作为整批初审的前置条件。")
    keyword = st.text_input("查找填写、手写、签章、论文或项目要求", key="m30_rule_query")
    attachment = st.selectbox("按附件筛选", range(19), format_func=lambda n: "全部附件及通则" if n == 0 else f"附件{n}", key="m30_rule_attachment")
    matching = [r for r in rulebook["rules"] if (not attachment or r["attachment"] == attachment)
                and (not keyword or keyword.casefold() in (r["text"] + r["section"] + r["id"]).casefold())]
    st.caption(f"共{len(matching)}项；展开查看完整要求与出处。")
    for rule in matching:
        with st.expander(f"{rule['id']} · {rule['text'][:64]}"):
            st.caption(review.rule_source(rule, rulebook))
            st.write(rule["text"])
    with st.expander("完整清单与认定表"):
        st.markdown(rulebook["markdown"])
    with st.expander("附件1至18索引"):
        st.dataframe([{"附件": a["id"], "文件名": a["filename"]} for a in rulebook["attachments"]], hide_index=True, width="stretch")
    with st.expander("参编规划教材字数辅助核对"):
        st.caption("仅在教育部审批规划教材、参与身份及字数证明已核实时适用；其他条件仍逐项检查。")
        words = st.number_input("个人参与字数", min_value=0, value=50000, step=1000, key="m30_words")
        st.write(review.textbook_credit(words, rulebook["settings"]))
    st.download_button("下载完整规则清单", rulebook["markdown"], f"职称评审规则_{rulebook['year']}.md", "text/markdown", key="m30_rules_download")

with receipt_tab:
    st.dataframe(review.summary_rows(document), hide_index=True, width="stretch")
    st.caption("已有收件记录仅说明收到材料，纸质、电子未知时保留待确认。")
    with st.expander("登记新收件"):
        with st.form("m30_new_case"):
            cols = st.columns([2, 2, 2])
            name = cols[0].text_input("姓名")
            department = cols[1].text_input("部门")
            received = cols[2].date_input("收到材料日期", value=date.fromisoformat(review.now()[:10]))
            note = st.text_input("收件备注")
            submitted = st.form_submit_button("登记收件", disabled=has_draft)
        if submitted:
            if not name.strip():
                st.error("请填写姓名。")
            elif any(c["name"] == name.strip() and c["department"] == department.strip() for c in document["cases"]):
                st.warning("已有同姓名、同部门记录，请到逐人初审中更新，避免重复登记。")
            else:
                case = review.new_case(name, received.isoformat(), document["year"])
                case.update(department=department.strip(), note=note)
                persist(review.update_case(document, case, "登记收件"))

with review_tab:
    if not document["cases"]:
        st.info("先在收件台账中登记人员。")
    else:
        cases_by_id = {c["id"]: c for c in document["cases"]}
        case_id = st.selectbox("选择申报人", list(cases_by_id),
                               format_func=lambda cid: f"{cases_by_id[cid]['name']} · {cases_by_id[cid]['department'] or '部门待确认'} · {cases_by_id[cid]['stage']}",
                               key="m30_case_id")
        case = cases_by_id[case_id]
        prefix = "m30_" + case_id
        with st.expander("申报路径与收件情况", expanded=True):
            with st.form(prefix + "_profile"):
                cols = st.columns(3)
                with cols[0]:
                    department = st.text_input("部门", case["department"], key=prefix + "_department")
                    level = choice("申报级别", review.LEVELS, case["level"], prefix + "_level")
                    paper = choice("纸质材料", review.RECEIPTS, case["paper"], prefix + "_paper")
                with cols[1]:
                    track = choice("岗位类别", review.TRACKS, case["track"], prefix + "_track")
                    route = choice("申报方式", review.ROUTES, case["route"], prefix + "_route")
                    electronic = choice("电子材料", review.RECEIPTS, case["electronic"], prefix + "_electronic")
                with cols[2]:
                    received = st.date_input("收件日期", date.fromisoformat(case["received_on"]) if case["received_on"] else None, key=prefix + "_received")
                    stage = choice("人工记录的工作状态", review.STAGES, case["stage"], prefix + "_stage")
                    certificate = choice("教师资格证", review.CERTIFICATES, case["certificate"], prefix + "_certificate")
                note = st.text_area("备注", case["note"], key=prefix + "_note")
                save_profile = st.form_submit_button("保存申报与收件情况", disabled=has_draft)
            if save_profile:
                edited = deepcopy(case)
                edited.update(department=department.strip(), level=level, track=track, route=route,
                              paper=paper, electronic=electronic, stage=stage, certificate=certificate,
                              received_on=received.isoformat() if received else "", note=note)
                persist(review.update_case(document, edited, "更新申报路径与收件情况"))
        st.info(review.certificate_guidance(case["level"], case["certificate"], rulebook["settings"]))
        with st.expander("本路径材料提示"):
            for item in review.expected_materials(case):
                st.write("• " + item)
        with st.expander("通常方案与替代方案核验"):
            st.caption("一般教师、思政课教师正常申报时，两套完整方案满足任一即可；硕士满3年也一样。辅导员、破格及转评按各自条款核验。")
            st.write(review.normal_scheme_result(case["normal_scheme"], case["alternative_scheme"]))
            with st.form(prefix + "_schemes"):
                normal = choice("方案一 通常必备条件＋任选1条", review.SCHEME_RESULTS, case["normal_scheme"], prefix + "_normal")
                alternative = choice("方案二 非论文必备条件＋替代论文门槛＋任选2条", review.SCHEME_RESULTS, case["alternative_scheme"], prefix + "_alternative")
                evidence = st.text_area("逐项核对的材料位置与事实", case["scheme_evidence"], key=prefix + "_scheme_evidence")
                save_schemes = st.form_submit_button("保存方案核验", disabled=has_draft)
            if save_schemes:
                if "符合" in (normal, alternative) and not evidence.strip():
                    st.error("标为符合时，请写明逐项核验依据，不能只凭毕业满3年或材料数量判断。")
                else:
                    edited = deepcopy(case)
                    edited.update(normal_scheme=normal, alternative_scheme=alternative, scheme_evidence=evidence)
                    persist(review.update_case(document, edited, "更新两套方案核验"))
        with st.expander("电子材料文字定位"):
            st.caption("支持PDF、DOCX、XLSX、UTF-8文本及ZIP。旧版Office或扫描图片会登记为需人工读取。"
                       "原文件与提取文字用于本次会话查看；保存的是文件清单、核验事实和结论，请保留原文件。单文件20 MiB、ZIP 50 MiB。")
            uploads = st.file_uploader("选择本人的材料", type=["pdf", "docx", "xlsx", "txt", "md", "csv", "doc", "xls", "png", "jpg", "jpeg", "zip"],
                                       accept_multiple_files=True, key=prefix + "_upload")
            if st.button("提取文字并预览文件清单", key=prefix + "_extract", disabled=not uploads):
                st.session_state.pop(prefix + "_preview", None)
                try:
                    if len(uploads) > 30 or sum(f.size for f in uploads) > 100 * 1024 * 1024:
                        raise ValueError("一次最多30个文件、合计100 MiB，请分批核阅。")
                    preview = []
                    for uploaded in uploads:
                        preview.extend(review.extract_upload(uploaded.name, uploaded.getvalue()))
                        if len(preview) > 100 or sum(len(s["text"]) for r in preview for s in r["segments"]) > 2_000_000:
                            raise ValueError("本批文件或文字较多，请分批核阅。")
                    st.session_state[prefix + "_preview"] = preview
                except (ValueError, OSError, RuntimeError):
                    st.error("本批未完成读取，请按容量限制分批，或提供可读取副本。已有记录保留。")
            preview = st.session_state.get(prefix + "_preview", [])
            if preview:
                st.dataframe([{"文件": r["metadata"]["filename"], "状态": r["metadata"]["status"], "说明": r["metadata"]["message"]} for r in preview], hide_index=True, width="stretch")
                index = st.selectbox("查看文件文字", range(len(preview)), format_func=lambda i: preview[i]["metadata"]["filename"], key=prefix + "_preview_index")
                query = st.text_input("在文件中定位关键词", key=prefix + "_material_query")
                segments = [s for s in preview[index]["segments"] if not query or query.casefold() in s["text"].casefold()]
                st.text_area("提取文字与位置", "\n\n".join(s["location"] + "\n" + s["text"] for s in segments), height=260,
                             key=prefix + "_text_" + preview[index]["metadata"]["id"] + "_" + hashlib.sha256(query.encode()).hexdigest()[:10], disabled=True)
                if st.button("保存文件清单", key=prefix + "_save_files", disabled=has_draft):
                    edited = deepcopy(case)
                    by_id = {m["id"]: m for m in case["materials"]}
                    by_id.update({r["metadata"]["id"]: r["metadata"] for r in preview})
                    edited["materials"] = list(by_id.values())
                    persist(review.update_case(document, edited, "登记电子文件清单"))
            if case["materials"]:
                st.caption(f"已保存{len(case['materials'])}份文件记录，文字提取状态不等于材料合格。")
        st.markdown("#### 逐项核验与待补问题")
        cols = st.columns([2, 3])
        selected_attachment = cols[0].selectbox("核验范围", range(19), format_func=lambda n: "全部附件及通则" if n == 0 else f"附件{n}", key=prefix + "_check_attachment")
        search = cols[1].text_input("定位核验项", key=prefix + "_check_search")
        options = [r for r in rulebook["rules"] if (not selected_attachment or r["attachment"] == selected_attachment)
                   and (not search or search.casefold() in (r["text"] + r["id"]).casefold())]
        if options:
            by_id = {r["id"]: r for r in options}
            rule_id = st.selectbox("核验条目", list(by_id), format_func=lambda rid: f"{rid} · {by_id[rid]['text'][:70]}", key=prefix + "_rule_id")
            st.write(by_id[rule_id]["text"])
            st.caption("出处：" + review.rule_source(by_id[rule_id], rulebook))
            check = case["checks"].get(rule_id, {"status": "未核验", "evidence": "", "note": ""})
            with st.form(prefix + "_check_" + rule_id):
                status = choice("核验结论", review.CHECK_STATUSES, check["status"], prefix + "_status_" + rule_id)
                evidence = st.text_area("材料文件、页码或单元格及事实", check["evidence"], key=prefix + "_evidence_" + rule_id)
                note = st.text_area("需修改、补证或咨询的内容", check["note"], key=prefix + "_check_note_" + rule_id)
                save_check = st.form_submit_button("保存本项核验", disabled=has_draft)
            if save_check:
                if status != "未核验" and not evidence.strip():
                    st.error("请写明材料位置和事实；不适用也应说明原因。")
                else:
                    edited = deepcopy(case)
                    edited["checks"][rule_id] = {"status": status, "evidence": evidence, "note": note,
                                                "updated_at": review.now(), "rule_version": rulebook["version"]}
                    persist(review.update_case(document, edited, "更新核验项 " + rule_id))
        else:
            st.caption("没有匹配的规则，请调整筛选。")
        st.download_button("导出本人的初审记录", review.review_report(case, rulebook),
                           f"{case['name']}_职称初审记录.md", "text/markdown", key=prefix + "_report")

with summary_tab:
    rows = review.summary_rows(document)
    st.dataframe(rows, hide_index=True, width="stretch")
    issues = [{"姓名": c["name"], "条目": rid, "状态": check["status"], "材料事实": check["evidence"], "待处理": check["note"]}
              for c in document["cases"] for rid, check in c["checks"].items()
              if check["status"] in {"待补材料", "待纸质核验", "待口径确认", "存在明确矛盾"}]
    st.markdown("#### 当前待处理问题")
    if issues:
        st.dataframe(issues, hide_index=True, width="stretch")
    else:
        st.caption("尚无已记录的问题；未核验的材料不能据此判为符合。")
    st.download_button("导出收件与初审汇总", review.summary_csv(document), f"职称评审汇总_{document['year']}.csv", "text/csv", key="m30_summary_download")
    st.download_button("导出完整工作记录备份", json.dumps(document, ensure_ascii=False, indent=2),
                       f"职称评审记录_{document['year']}.json", "application/json", key="m30_backup_download")
