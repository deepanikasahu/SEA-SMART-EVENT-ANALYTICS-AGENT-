"""
Agent Orchestration Loop for Smart Event Analytics Agent.
Builds a transparent, native tool-calling loop with zero framework abstractions.
Handles intent parsing, clarification triggers, dynamic tool execution,
deterministic metric calculation, LLM reasoning, and validation.
"""

import json
import logging
import os
import time
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd

from agent.llm_client import BaseLLMAdapter, ToolCall, LLMResponse, get_llm_adapter
from agent.tools import (
    AGENT_TOOLS_SCHEMA,
    get_events,
    get_registrations,
    get_attendance,
    get_feedback,
    get_club_plans,
    get_database_summary
)
from agent.metrics import compute_club_metrics, compute_event_level_stats
from agent.ranking import rank_clubs, load_weights_config
from agent.explain import generate_ranking_explanation

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")
logger = logging.getLogger(__name__)


ORCHESTRATOR_SYSTEM_PROMPT = """You are the autonomous Smart Event Analytics Agent orchestrator.
Your goal is to parse the user's natural language request and systematically call tools to collect event data from the database.

AVAILABLE TOOLS:
1. `get_events(start_date, end_date, category)`: Fetches events within the date range and category.
2. `get_registrations(event_ids)`: Fetches registrations for the selected event IDs.
3. `get_attendance(event_ids)`: Fetches attendance records for the selected event IDs.
4. `get_feedback(event_ids)`: Fetches feedback ratings and comments for the selected event IDs.
5. `get_club_plans()`: Fetches planned event targets per club.

EXECUTION RULES:
- If the user query does NOT specify any time period, semester, or date range at all, DO NOT guess silently. Respond asking for clarification on the time period.
- For queries referring to "last semester" or recent semester, use start_date="2024-01-15" and end_date="2024-05-30".
- For category requests (e.g. "technical events"), set category="Technical".
- After discovering relevant events, call the corresponding tools (`get_registrations`, `get_attendance`, `get_feedback`, and `get_club_plans`) with the retrieved event_ids.
- Once all tools have returned their data, summarize that data collection is complete.
"""


class EventAnalyticsAgent:
    """
    Core AI Agent implementing the goal-directed tool-calling loop and deterministic pipeline.
    """
    def __init__(
        self,
        db_path: str = "data/sea_agent.db",
        weights_path: str = "weights_config.json",
        provider: Optional[str] = None,
        impute_missing: bool = False
    ):
        self.db_path = db_path
        self.weights_path = weights_path
        self.impute_missing = impute_missing
        self.llm_adapter = get_llm_adapter(provider)
        self.weights_config = load_weights_config(weights_path)

    def _execute_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Tuple[Any, str]:
        """Execute Python tool function and return structured object and JSON string for LLM."""
        logger.info(f"Executing Tool: {tool_name} with args: {arguments}")
        
        if tool_name == "get_events":
            res = get_events(
                start_date=arguments.get("start_date"),
                end_date=arguments.get("end_date"),
                category=arguments.get("category"),
                club_id=arguments.get("club_id") or arguments.get("club_name"),
                db_path=self.db_path
            )
            if isinstance(res, dict) and "error" in res:
                return res, json.dumps(res)
            df = res
            # Compact summary to avoid token bloat and 429 rate limits
            summary = {
                "total_events_found": len(df),
                "event_ids": df["event_id"].tolist() if not df.empty else [],
                "clubs_represented": df["club_name"].nunique() if not df.empty else 0
            }
            return df, json.dumps(summary)


        elif tool_name == "get_registrations":
            event_ids = arguments.get("event_ids")
            res = get_registrations(event_ids=event_ids, db_path=self.db_path)
            if isinstance(res, dict) and "error" in res:
                return res, json.dumps(res)
            df = res
            # Send summary count to LLM to keep context token-efficient
            summary = {
                "total_registrations_found": len(df),
                "event_ids_covered": df["event_id"].nunique() if not df.empty else 0
            }
            return df, json.dumps(summary)

        elif tool_name == "get_attendance":
            event_ids = arguments.get("event_ids")
            res = get_attendance(event_ids=event_ids, db_path=self.db_path)
            if isinstance(res, dict) and "error" in res:
                return res, json.dumps(res)
            df = res
            summary = {
                "total_attendance_records": len(df),
                "actual_attendees_count": int(df[df["attended"] == 1].shape[0]) if not df.empty else 0,
                "events_with_attendance_records": df["event_id"].nunique() if not df.empty else 0
            }
            return df, json.dumps(summary)

        elif tool_name == "get_feedback":
            event_ids = arguments.get("event_ids")
            res = get_feedback(event_ids=event_ids, db_path=self.db_path)
            if isinstance(res, dict) and "error" in res:
                return res, json.dumps(res)
            df = res
            summary = {
                "total_feedback_responses": len(df),
                "average_overall_rating": round(float(df["rating"].mean()), 2) if not df.empty else 0.0,
                "events_with_feedback_records": df["event_id"].nunique() if not df.empty else 0
            }
            return df, json.dumps(summary)

        elif tool_name == "get_club_plans":
            res = get_club_plans(
                club_id=arguments.get("club_id") or arguments.get("club_name"),
                db_path=self.db_path
            )
            if isinstance(res, dict) and "error" in res:
                return res, json.dumps(res)
            df = res
            data_list = df.to_dict(orient="records")
            return df, json.dumps(data_list)

        else:
            err_msg = f"Unknown tool '{tool_name}' requested."
            logger.error(err_msg)
            return pd.DataFrame(), json.dumps({"error": err_msg})

    def run(self, user_query: str, max_turns: int = 5) -> Dict[str, Any]:
        """
        Execute the end-to-end autonomous agent workflow for a given user query.
        
        Returns:
            Dict containing full audit trail, computed rankings, narrative, and reports.
        """
        start_time = time.time()
        logger.info(f"Agent received user query: '{user_query}'")

        # Initial validation: Check if time period is completely omitted
        has_time_indication = any(
            token in user_query.lower() for token in [
                "semester", "term", "202", "month", "last", "from", "between",
                "spring", "fall", "autumn", "summer", "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"
            ]
        )

        execution_log = []
        messages = [
            {"role": "system", "content": ORCHESTRATOR_SYSTEM_PROMPT},
            {"role": "user", "content": user_query}
        ]

        # Collected Dataframes
        collected_data = {
            "events": pd.DataFrame(),
            "registrations": pd.DataFrame(),
            "attendance": pd.DataFrame(),
            "feedback": pd.DataFrame(),
            "club_plans": pd.DataFrame()
        }

        # Step 1: Autonomous Tool-Calling Loop
        turn = 0
        clarification_prompt = None
        cap_hit = False
        llm_notice = None

        if max_turns <= 0:
            cap_hit = True

        while turn < max_turns and not cap_hit:
            turn += 1
            logger.info(f"Starting Tool-Calling Iteration {turn}/{max_turns}...")
            
            try:
                response: LLMResponse = self.llm_adapter.call_with_tools(
                    messages=messages,
                    tools=AGENT_TOOLS_SCHEMA,
                    tool_choice="auto"
                )
            except Exception as e:
                raw_err = str(e)
                if hasattr(self.llm_adapter, "api_key") and self.llm_adapter.api_key:
                    raw_err = raw_err.replace(self.llm_adapter.api_key, "[REDACTED]")
                logger.warning(f"LLM tool calling failed: {raw_err}. Falling back to deterministic execution.")
                llm_notice = f"LLM provider call failed ({self.llm_adapter.__class__.__name__}): {raw_err}. Fell back to deterministic execution and ranking."
                execution_log.append({
                    "step": "LLM Fallback Triggered",
                    "detail": f"Provider call failed; proceeding with deterministic execution. Notice: {llm_notice}"
                })
                # Fallback to deterministic event & dependent data retrieval
                if collected_data["events"].empty:
                    cat = "Technical" if "technical" in user_query.lower() else ("Cultural" if "cultural" in user_query.lower() else None)
                    df_res, json_res = self._execute_tool_call("get_events", {
                        "start_date": "2024-01-15",
                        "end_date": "2024-05-30",
                        "category": cat
                    })
                    if isinstance(df_res, pd.DataFrame) and not df_res.empty:
                        collected_data["events"] = df_res
                        event_ids = df_res["event_id"].tolist()

                        # 1. Registrations
                        t_s = time.time()
                        reg_res = get_registrations(event_ids, self.db_path)
                        collected_data["registrations"] = reg_res if isinstance(reg_res, pd.DataFrame) else pd.DataFrame()
                        execution_log.append({
                            "step": "Tool Execution: get_registrations",
                            "name": "get_registrations",
                            "arguments": {"event_ids": event_ids, "event_ids_count": len(event_ids)},
                            "record_count": len(collected_data["registrations"]),
                            "records_fetched": len(collected_data["registrations"]),
                            "duration": round(time.time() - t_s, 3),
                            "duration_seconds": round(time.time() - t_s, 3)
                        })

                        # 2. Attendance
                        t_s = time.time()
                        att_res = get_attendance(event_ids, self.db_path)
                        collected_data["attendance"] = att_res if isinstance(att_res, pd.DataFrame) else pd.DataFrame()
                        execution_log.append({
                            "step": "Tool Execution: get_attendance",
                            "name": "get_attendance",
                            "arguments": {"event_ids": event_ids, "event_ids_count": len(event_ids)},
                            "record_count": len(collected_data["attendance"]),
                            "records_fetched": len(collected_data["attendance"]),
                            "duration": round(time.time() - t_s, 3),
                            "duration_seconds": round(time.time() - t_s, 3)
                        })

                        # 3. Feedback
                        t_s = time.time()
                        fb_res = get_feedback(event_ids, self.db_path)
                        collected_data["feedback"] = fb_res if isinstance(fb_res, pd.DataFrame) else pd.DataFrame()
                        execution_log.append({
                            "step": "Tool Execution: get_feedback",
                            "name": "get_feedback",
                            "arguments": {"event_ids": event_ids, "event_ids_count": len(event_ids)},
                            "record_count": len(collected_data["feedback"]),
                            "records_fetched": len(collected_data["feedback"]),
                            "duration": round(time.time() - t_s, 3),
                            "duration_seconds": round(time.time() - t_s, 3)
                        })

                        # 4. Club Plans
                        t_s = time.time()
                        cp_res = get_club_plans(db_path=self.db_path)
                        collected_data["club_plans"] = cp_res if isinstance(cp_res, pd.DataFrame) else pd.DataFrame()
                        execution_log.append({
                            "step": "Tool Execution: get_club_plans",
                            "name": "get_club_plans",
                            "arguments": {},
                            "record_count": len(collected_data["club_plans"]),
                            "records_fetched": len(collected_data["club_plans"]),
                            "duration": round(time.time() - t_s, 3),
                            "duration_seconds": round(time.time() - t_s, 3)
                        })
                break

            # Record assistant turn in trajectory
            assistant_msg: Dict[str, Any] = {"role": "assistant"}
            if response.content:
                assistant_msg["content"] = response.content
            if response.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}
                    }
                    for tc in response.tool_calls
                ]
            messages.append(assistant_msg)

            # If LLM didn't call any tools
            if not response.tool_calls:
                # Check if it was a clarification question or final statement
                if not has_time_indication or "clarif" in (response.content or "").lower() or "?" in (response.content or ""):
                    clarification_prompt = response.content
                    execution_log.append({
                        "step": f"Turn {turn}: Clarification Request",
                        "detail": response.content
                    })
                    break
                else:
                    # Model finished or produced text
                    execution_log.append({
                        "step": f"Turn {turn}: LLM Summary",
                        "detail": response.content
                    })
                    break

            # Execute tool calls
            for tc in response.tool_calls:
                tool_start = time.time()
                df_res, json_res = self._execute_tool_call(tc.name, tc.arguments)
                tool_dur = time.time() - tool_start

                if isinstance(df_res, pd.DataFrame):
                    record_count = len(df_res)
                elif isinstance(df_res, list):
                    record_count = len(df_res)
                elif isinstance(df_res, dict):
                    record_count = 0 if "error" in df_res else len(df_res)
                else:
                    record_count = 0

                # Log each tool call: name, arguments, record count, and duration in execution_log
                execution_log.append({
                    "step": f"Tool Execution: {tc.name}",
                    "name": tc.name,
                    "arguments": tc.arguments,
                    "record_count": record_count,
                    "records_fetched": record_count,
                    "duration": round(tool_dur, 3),
                    "duration_seconds": round(tool_dur, 3)
                })

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "content": json_res
                })

                # Store raw dataframes
                if tc.name == "get_events" and isinstance(df_res, pd.DataFrame):
                    collected_data["events"] = df_res
                    if not df_res.empty:
                        event_ids = df_res["event_id"].tolist()
                        
                        # 1. Registrations
                        t_s = time.time()
                        reg_res = get_registrations(event_ids, self.db_path)
                        collected_data["registrations"] = reg_res if isinstance(reg_res, pd.DataFrame) else pd.DataFrame()
                        execution_log.append({
                            "step": "Tool Execution: get_registrations",
                            "name": "get_registrations",
                            "arguments": {"event_ids": event_ids, "event_ids_count": len(event_ids)},
                            "record_count": len(collected_data["registrations"]),
                            "records_fetched": len(collected_data["registrations"]),
                            "duration": round(time.time() - t_s, 3),
                            "duration_seconds": round(time.time() - t_s, 3)
                        })

                        # 2. Attendance
                        t_s = time.time()
                        att_res = get_attendance(event_ids, self.db_path)
                        collected_data["attendance"] = att_res if isinstance(att_res, pd.DataFrame) else pd.DataFrame()
                        execution_log.append({
                            "step": "Tool Execution: get_attendance",
                            "name": "get_attendance",
                            "arguments": {"event_ids": event_ids, "event_ids_count": len(event_ids)},
                            "record_count": len(collected_data["attendance"]),
                            "records_fetched": len(collected_data["attendance"]),
                            "duration": round(time.time() - t_s, 3),
                            "duration_seconds": round(time.time() - t_s, 3)
                        })

                        # 3. Feedback
                        t_s = time.time()
                        fb_res = get_feedback(event_ids, self.db_path)
                        collected_data["feedback"] = fb_res if isinstance(fb_res, pd.DataFrame) else pd.DataFrame()
                        execution_log.append({
                            "step": "Tool Execution: get_feedback",
                            "name": "get_feedback",
                            "arguments": {"event_ids": event_ids, "event_ids_count": len(event_ids)},
                            "record_count": len(collected_data["feedback"]),
                            "records_fetched": len(collected_data["feedback"]),
                            "duration": round(time.time() - t_s, 3),
                            "duration_seconds": round(time.time() - t_s, 3)
                        })

                        # 4. Club Plans
                        t_s = time.time()
                        cp_res = get_club_plans(db_path=self.db_path)
                        collected_data["club_plans"] = cp_res if isinstance(cp_res, pd.DataFrame) else pd.DataFrame()
                        execution_log.append({
                            "step": "Tool Execution: get_club_plans",
                            "name": "get_club_plans",
                            "arguments": {},
                            "record_count": len(collected_data["club_plans"]),
                            "records_fetched": len(collected_data["club_plans"]),
                            "duration": round(time.time() - t_s, 3),
                            "duration_seconds": round(time.time() - t_s, 3)
                        })

                        logger.info("All dependent datasets collected in batch. Proceeding to computation.")
                        break
                elif tc.name == "get_registrations" and isinstance(df_res, pd.DataFrame):
                    collected_data["registrations"] = df_res
                elif tc.name == "get_attendance" and isinstance(df_res, pd.DataFrame):
                    collected_data["attendance"] = df_res
                elif tc.name == "get_feedback" and isinstance(df_res, pd.DataFrame):
                    collected_data["feedback"] = df_res
                elif tc.name == "get_club_plans" and isinstance(df_res, pd.DataFrame):
                    collected_data["club_plans"] = df_res

            # If all datasets populated, conclude outer tool-calling loop immediately
            if (not collected_data["events"].empty and 
                not collected_data["registrations"].empty and 
                not collected_data["attendance"].empty and 
                not collected_data["feedback"].empty and 
                not collected_data["club_plans"].empty):
                break

            # If we reached max_turns and the loop hasn't concluded
            if turn >= max_turns:
                cap_hit = True
                break

        # Check for cap-hit termination
        if cap_hit:
            msg = f"Maximum tool-calling iterations ({max_turns}) reached without completing data collection."
            logger.warning(msg)
            return {
                "status": "max_turns_reached",
                "message": msg,
                "execution_log": execution_log,
                "duration_seconds": round(time.time() - start_time, 2)
            }



        # Check for clarification termination (Non-blocking, structured response for UI/CLI)
        if clarification_prompt and collected_data["events"].empty:
            q_text = clarification_prompt.strip()
            if not q_text:
                q_text = "Could you please specify the time period or semester (e.g., 'last semester' or '2024-01-15 to 2024-05-30') you want to analyze?"
            return {
                "status": "needs_clarification",
                "question": q_text,
                "message": q_text,
                "execution_log": execution_log,
                "duration_seconds": round(time.time() - start_time, 2)
            }


        # Fallback safeguard: if LLM only fetched events, automatically ensure dependent data is fetched
        if not collected_data["events"].empty:
            in_scope_event_ids = collected_data["events"]["event_id"].tolist()
            if collected_data["registrations"].empty:
                collected_data["registrations"] = get_registrations(in_scope_event_ids, self.db_path)
            if collected_data["attendance"].empty:
                collected_data["attendance"] = get_attendance(in_scope_event_ids, self.db_path)
            if collected_data["feedback"].empty:
                collected_data["feedback"] = get_feedback(in_scope_event_ids, self.db_path)
            if collected_data["club_plans"].empty:
                collected_data["club_plans"] = get_club_plans(self.db_path)

        # Step 2: Deterministic Metrics Calculation (Python/pandas only)
        logger.info("Computing deterministic club-level performance metrics...")
        metrics_df, audit_disclosures = compute_club_metrics(
            events_df=collected_data["events"],
            registrations_df=collected_data["registrations"],
            attendance_df=collected_data["attendance"],
            feedback_df=collected_data["feedback"],
            club_plans_df=collected_data["club_plans"],
            impute_missing=self.impute_missing
        )

        if metrics_df.empty:
            return {
                "status": "ERROR",
                "message": "No matching events found for the specified query.",
                "execution_log": execution_log
            }

        # Step 3: Deterministic Normalization & Ranking
        logger.info("Computing normalized scores and composite rankings...")
        ranked_df, ranking_meta = rank_clubs(metrics_df, config_path=self.weights_path)

        # Step 4: LLM Reasoning Layer (Grounded Explanation)
        logger.info("Generating grounded ranking explanation from pre-computed metrics...")
        ranked_records = ranked_df.to_dict(orient="records")
        in_scope_dates = []
        if not collected_data["events"].empty and "date" in collected_data["events"].columns:
            in_scope_dates = collected_data["events"]["date"].dropna().astype(str).tolist()

        try:
            explanation_text, validation_report = generate_ranking_explanation(
                ranked_metrics=ranked_records,
                weights_config=self.weights_config,
                llm_adapter=self.llm_adapter,
                audit_disclosures=audit_disclosures,
                in_scope_event_dates=in_scope_dates
            )
        except Exception as e:
            raw_err = str(e)
            if hasattr(self.llm_adapter, "api_key") and self.llm_adapter.api_key:
                raw_err = raw_err.replace(self.llm_adapter.api_key, "[REDACTED]")
            logger.warning(f"LLM explanation generation failed: {raw_err}. Using deterministic explanation fallback.")
            if not llm_notice:
                llm_notice = f"LLM explanation call failed ({self.llm_adapter.__class__.__name__}): {raw_err}. Displaying deterministic rankings."
            from agent.llm_client import MockLLMAdapter
            mock_adapter = MockLLMAdapter()
            explanation_text, validation_report = generate_ranking_explanation(
                ranked_metrics=ranked_records,
                weights_config=self.weights_config,
                llm_adapter=mock_adapter,
                audit_disclosures=audit_disclosures,
                in_scope_event_dates=in_scope_dates
            )

        # Event-level details for report audit section
        event_stats_df = compute_event_level_stats(
            collected_data["events"],
            collected_data["registrations"],
            collected_data["attendance"],
            collected_data["feedback"]
        )

        total_duration = time.time() - start_time
        logger.info(f"Agent execution completed in {round(total_duration, 2)}s.")

        return {
            "status": "SUCCESS",
            "query": user_query,
            "provider": self.llm_adapter.__class__.__name__,
            "total_duration_seconds": round(total_duration, 2),
            "execution_log": execution_log,
            "in_scope_events_count": len(collected_data["events"]),
            "ranked_clubs": ranked_records,
            "ranking_metadata": ranking_meta,
            "audit_disclosures": audit_disclosures,
            "grounded_narrative": explanation_text,
            "number_grounding_audit": validation_report,
            "event_stats": event_stats_df.to_dict(orient="records"),
            "weights_config": self.weights_config,
            "llm_notice": llm_notice
        }
