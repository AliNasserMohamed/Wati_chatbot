import logging
import json
import os
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List, Union
from pathlib import Path
import traceback


class MessageJourneyLogger:
    """
    Comprehensive logging system for tracking message journey through the chatbot.
    Logs the complete lifecycle from incoming message to final response.
    """
    
    def __init__(self):
        self.setup_logging()
        self.active_journeys: Dict[str, Dict[str, Any]] = {}
    
    def setup_logging(self):
        """Setup logging configuration with file rotation"""
        # Create logs directory
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # Setup main message journey logger
        self.logger = logging.getLogger("message_journey")
        self.logger.setLevel(logging.INFO)
        
        # Remove existing handlers to avoid duplicates
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        # Create date-based log file
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = log_dir / f"message_journey_{today}.log"
        
        # File handler with detailed formatting
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        
        # Console handler for real-time monitoring
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Detailed formatter with timestamp and context
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        # Ensure the logger doesn't propagate to avoid duplicate logs
        self.logger.propagate = False
        
        self.logger.info("🚀 MessageJourneyLogger initialized")
    
    def start_journey(self, 
                      phone_number: str, 
                      message_text: str,
                      wati_message_id: Optional[str] = None,
                      message_type: str = "text",
                      webhook_data: Optional[Dict] = None) -> str:
        """
        Start tracking a new message journey.
        Returns a unique journey_id for tracking this message.
        """
        journey_id = f"msg_{uuid.uuid4().hex[:12]}"
        
        journey_data = {
            "journey_id": journey_id,
            "phone_number": phone_number,
            "message_text": message_text,
            "wati_message_id": wati_message_id,
            "message_type": message_type,
            "started_at": datetime.now().isoformat(),
            "steps": [],
            "status": "started",
            "webhook_data": webhook_data or {}
        }
        
        self.active_journeys[journey_id] = journey_data
        
        # Log the start of journey
        self.logger.info(f"📥 JOURNEY_START | ID: {journey_id} | Phone: {phone_number} | Type: {message_type}")
        self.logger.info(f"📝 MESSAGE_RECEIVED | ID: {journey_id} | Text: '{message_text[:100]}{'...' if len(message_text) > 100 else ''}'")
        
        if wati_message_id:
            self.logger.info(f"🆔 WATI_MESSAGE_ID | ID: {journey_id} | Wati ID: {wati_message_id}")
            
        return journey_id
    
    def add_step(self,
                 journey_id: str,
                 step_type: str,
                 description: str,
                 data: Optional[Dict] = None,
                 status: str = "completed",
                 duration_ms: Optional[int] = None):
        """Add a processing step to the message journey"""
        if journey_id not in self.active_journeys:
            self.logger.warning(f"⚠️ Journey {journey_id} not found, creating minimal journey")
            self.active_journeys[journey_id] = {
                "journey_id": journey_id,
                "started_at": datetime.now().isoformat(),
                "steps": [],
                "status": "active"
            }
        
        step = {
            "step_type": step_type,
            "description": description,
            "timestamp": datetime.now().isoformat(),
            "status": status,
            "data": data or {},
            "duration_ms": duration_ms
        }
        
        self.active_journeys[journey_id]["steps"].append(step)
        
        # Format duration info
        duration_info = f" | Duration: {duration_ms}ms" if duration_ms else ""
        
        # Log the step
        self.logger.info(f"🔄 {step_type.upper()} | ID: {journey_id} | {description}{duration_info}")
        
        # Log additional data if provided
        if data and isinstance(data, dict):
            for key, value in data.items():
                if key in ['error', 'exception']:
                    self.logger.error(f"❌ {step_type.upper()}_ERROR | ID: {journey_id} | {key}: {value}")
                elif key == 'confidence' and isinstance(value, (int, float)):
                    self.logger.info(f"🎯 {step_type.upper()}_CONFIDENCE | ID: {journey_id} | Score: {value:.3f}")
                elif key in ['prompt', 'response'] and isinstance(value, str):
                    truncated_value = value[:200] + "..." if len(value) > 200 else value
                    self.logger.info(f"💬 {step_type.upper()}_{key.upper()} | ID: {journey_id} | Content: '{truncated_value}'")
    
    def log_embedding_agent(self,
                           journey_id: str,
                           user_message: str,
                           action: str,
                           confidence: float,
                           matched_question: Optional[str] = None,
                           response: Optional[str] = None,
                           duration_ms: Optional[int] = None):
        """Log embedding agent processing"""
        self.add_step(
            journey_id=journey_id,
            step_type="embedding_agent",
            description=f"Embedding agent processing - Action: {action}",
            data={
                "action": action,
                "confidence": confidence,
                "matched_question": matched_question,
                "response": response[:100] + "..." if response and len(response) > 100 else response
            },
            duration_ms=duration_ms
        )
    
    def log_classification(self,
                          journey_id: str,
                          message_text: str,
                          classified_type: str,
                          detected_language: str,
                          confidence: Optional[float] = None,
                          duration_ms: Optional[int] = None):
        """Log message classification"""
        self.add_step(
            journey_id=journey_id,
            step_type="message_classification",
            description=f"Classified as {classified_type} in {detected_language}",
            data={
                "classified_type": classified_type,
                "detected_language": detected_language,
                "confidence": confidence,
                "message_length": len(message_text)
            },
            duration_ms=duration_ms
        )
    
    def log_agent_processing(self,
                           journey_id: str,
                           agent_name: str,
                           action: str,
                           input_data: Optional[Dict] = None,
                           output_data: Optional[Dict] = None,
                           duration_ms: Optional[int] = None,
                           status: str = "completed"):
        """Log agent processing (query_agent, service_request_agent, etc.)"""
        self.add_step(
            journey_id=journey_id,
            step_type=f"{agent_name}_processing",
            description=f"{agent_name} - {action}",
            data={
                "agent": agent_name,
                "action": action,
                "input": input_data,
                "output": output_data,
                "status": status
            },
            duration_ms=duration_ms,
            status=status
        )
    
    def log_llm_interaction(self,
                          journey_id: str,
                          llm_type: str,  # "openai", "gemini", etc.
                          prompt: str,
                          response: str,
                          model: Optional[str] = None,
                          function_calls: Optional[List] = None,
                          duration_ms: Optional[int] = None,
                          tokens_used: Optional[Dict] = None):
        """Log LLM API interactions"""
        self.add_step(
            journey_id=journey_id,
            step_type="llm_interaction",
            description=f"LLM call to {llm_type}" + (f" ({model})" if model else ""),
            data={
                "llm_type": llm_type,
                "model": model,
                "prompt": prompt[:500] + "..." if len(prompt) > 500 else prompt,
                "response": response[:500] + "..." if len(response) > 500 else response,
                "function_calls": function_calls,
                "tokens_used": tokens_used,
                "prompt_length": len(prompt),
                "response_length": len(response)
            },
            duration_ms=duration_ms
        )
    
    def log_database_operation(self,
                             journey_id: str,
                             operation: str,  # "save_message", "create_reply", "get_history"
                             table: str,
                             details: Optional[Dict] = None,
                             duration_ms: Optional[int] = None,
                             status: str = "completed"):
        """Log database operations"""
        self.add_step(
            journey_id=journey_id,
            step_type="database_operation",
            description=f"Database {operation} on {table}",
            data={
                "operation": operation,
                "table": table,
                "details": details
            },
            duration_ms=duration_ms,
            status=status
        )
    
    def log_whatsapp_send(self,
                         journey_id: str,
                         phone_number: str,
                         message: str,
                         status: str,
                         response_data: Optional[Dict] = None,
                         duration_ms: Optional[int] = None,
                         error: Optional[str] = None):
        """Log WhatsApp message sending"""
        self.add_step(
            journey_id=journey_id,
            step_type="whatsapp_send",
            description=f"Send message to {phone_number} - Status: {status}",
            data={
                "phone_number": phone_number,
                "message": message[:100] + "..." if len(message) > 100 else message,
                "message_length": len(message),
                "status": status,
                "response_data": response_data,
                "error": error
            },
            duration_ms=duration_ms,
            status="failed" if error else "completed"
        )
    
    def log_error(self,
                  journey_id: str,
                  error_type: str,
                  error_message: str,
                  step: Optional[str] = None,
                  exception: Optional[Exception] = None):
        """Log errors during message processing"""
        error_data = {
            "error_type": error_type,
            "error_message": error_message,
            "step": step
        }
        
        if exception:
            error_data["exception_type"] = type(exception).__name__
            error_data["traceback"] = traceback.format_exc()
        
        self.add_step(
            journey_id=journey_id,
            step_type="error",
            description=f"Error in {step or 'unknown step'}: {error_message}",
            data=error_data,
            status="failed"
        )
        
        if journey_id in self.active_journeys:
            self.active_journeys[journey_id]["status"] = "failed"
    
    def complete_journey(self,
                        journey_id: str,
                        final_response: Optional[str] = None,
                        status: str = "completed"):
        """Mark journey as completed and log final summary"""
        if journey_id not in self.active_journeys:
            self.logger.warning(f"⚠️ Journey {journey_id} not found for completion")
            return
        
        journey = self.active_journeys[journey_id]
        journey["status"] = status
        journey["completed_at"] = datetime.now().isoformat()
        
        if final_response:
            journey["final_response"] = final_response
        
        # Calculate total journey duration
        start_time = datetime.fromisoformat(journey["started_at"])
        end_time = datetime.now()
        total_duration = int((end_time - start_time).total_seconds() * 1000)
        
        journey["total_duration_ms"] = total_duration
        
        # Log completion summary
        self.logger.info(f"✅ JOURNEY_COMPLETE | ID: {journey_id} | Status: {status} | Duration: {total_duration}ms | Steps: {len(journey['steps'])}")
        
        if final_response:
            response_preview = final_response[:100] + "..." if len(final_response) > 100 else final_response
            self.logger.info(f"📤 FINAL_RESPONSE | ID: {journey_id} | Response: '{response_preview}'")
        
        # Keep the journey data for a while for potential debugging
        # In production, you might want to archive or clean old journeys
    
    def get_journey_summary(self, journey_id: str) -> Optional[Dict]:
        """Get a summary of a specific journey"""
        if journey_id not in self.active_journeys:
            return None
        
        journey = self.active_journeys[journey_id].copy()
        
        # Add some computed statistics
        journey["total_steps"] = len(journey["steps"])
        
        step_types = {}
        for step in journey["steps"]:
            step_type = step["step_type"]
            step_types[step_type] = step_types.get(step_type, 0) + 1
        
        journey["step_types_count"] = step_types
        
        return journey
    
    def cleanup_old_journeys(self, max_age_hours: int = 24):
        """Clean up old journey data to prevent memory bloat"""
        current_time = datetime.now()
        to_remove = []
        
        for journey_id, journey in self.active_journeys.items():
            try:
                start_time = datetime.fromisoformat(journey["started_at"])
                age_hours = (current_time - start_time).total_seconds() / 3600
                
                if age_hours > max_age_hours:
                    to_remove.append(journey_id)
            except Exception as e:
                # If there's an issue with the timestamp, remove it
                to_remove.append(journey_id)
        
        for journey_id in to_remove:
            del self.active_journeys[journey_id]
        
        if to_remove:
            self.logger.info(f"🧹 Cleaned up {len(to_remove)} old journey records")

    def log_function_call(self,
                         journey_id: str,
                         function_name: str,
                         function_args: Dict[str, Any],
                         function_result: Any,
                         duration_ms: Optional[int] = None,
                         status: str = "completed",
                         error: Optional[str] = None):
        """Log individual function calls and their responses"""
        self.add_step(
            journey_id=journey_id,
            step_type="function_call",
            description=f"Function call: {function_name}",
            data={
                "function_name": function_name,
                "arguments": function_args,
                "result": function_result if isinstance(function_result, (dict, list, str, int, float, bool)) else str(function_result),
                "result_type": type(function_result).__name__,
                "error": error,
                "status": status
            },
            duration_ms=duration_ms,
            status=status
        )
        
        # Additional detailed logging for function calls
        args_str = json.dumps(function_args, ensure_ascii=False, indent=None)[:200]
        if len(args_str) >= 200:
            args_str += "..."
            
        self.logger.info(f"🔧 FUNCTION_CALL | ID: {journey_id} | Function: {function_name} | Args: {args_str}")
        
        if error:
            self.logger.error(f"❌ FUNCTION_ERROR | ID: {journey_id} | Function: {function_name} | Error: {error}")
        elif isinstance(function_result, dict) and function_result.get('success'):
            result_summary = f"Success: {len(function_result.get('data', []))} items" if 'data' in function_result else "Success"
            self.logger.info(f"✅ FUNCTION_SUCCESS | ID: {journey_id} | Function: {function_name} | Result: {result_summary}")
        elif isinstance(function_result, dict) and not function_result.get('success'):
            error_msg = function_result.get('error', 'Unknown error')
            self.logger.warning(f"⚠️ FUNCTION_PARTIAL | ID: {journey_id} | Function: {function_name} | Issue: {error_msg}")
        else:
            result_str = str(function_result)[:100]
            if len(str(function_result)) > 100:
                result_str += "..."
            self.logger.info(f"📋 FUNCTION_RESULT | ID: {journey_id} | Function: {function_name} | Result: {result_str}")


# Create global instance
message_journey_logger = MessageJourneyLogger() 