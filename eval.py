import os
import re
import sys
import time
import psutil
import signal
import asyncio
import logging
import tempfile
import traceback
import threading
import subprocess
from functools import (
    wraps
)
from http.server import (
    HTTPServer,
    BaseHTTPRequestHandler
)
from typing import (
    Any,
    Dict,
    Tuple,
    Optional
)

from telegram import (
    Update,
    Message,
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    filters,
    Application,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler
)
from telegram.error import (
    TimedOut,
    BadRequest,
    Forbidden,
    TelegramError,
    NetworkError,
    ChatMigrated
)

# BOT CONFIGURATION
BOT_USERNAME = "iCodeEvalBot"  # Replace with your bot username
UPDATES_CHANNEL = "https://t.me/WorkGlows"
SUPPORT_GROUP = "https://t.me/SoulMeetsHQ"
MAX_MESSAGE_LENGTH = 400  # Character limit for messages

# Color codes for logging
class Colors:
    BLUE = '\033[94m'      # INFO/WARNING
    GREEN = '\033[92m'     # DEBUG
    YELLOW = '\033[93m'    # INFO
    RED = '\033[91m'       # ERROR
    RESET = '\033[0m'      # Reset color
    BOLD = '\033[1m'       # Bold text

class ColoredFormatter(logging.Formatter):
    """Custom formatter to add colors to entire log messages"""

    COLORS = {
        'DEBUG': Colors.GREEN,
        'INFO': Colors.YELLOW,
        'WARNING': Colors.BLUE,
        'ERROR': Colors.RED,
    }

    def format(self, record):
        # Get the original formatted message
        original_format = super().format(record)

        # Get color based on log level
        color = self.COLORS.get(record.levelname, Colors.RESET)

        # Apply color to the entire message
        colored_format = f"{color}{original_format}{Colors.RESET}"

        return colored_format

# Configure logging with colors
def setup_colored_logging():
    """Setup colored logging configuration"""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)

    # Create colored formatter with enhanced format
    formatter = ColoredFormatter(
        fmt='%(asctime)s - %(name)s - [%(levelname)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(console_handler)

    return logger

# Initialize colored logger
logger = setup_colored_logging()

# UTILITY FUNCTIONS
def extract_user_info(msg: Message) -> Dict[str, any]:
    """Extract user and chat information from message"""
    try:
        logger.debug("🔍 Extracting user information from message")
        u = msg.from_user
        c = msg.chat
        
        if not u or not c:
            logger.warning("⚠️ Missing user or chat information in message")
            return {
                "user_id": "unknown",
                "username": "unknown",
                "full_name": "unknown",
                "chat_id": "unknown",
                "chat_type": "unknown",
                "chat_title": "unknown",
                "chat_username": "No Username",
                "chat_link": "No Link",
            }
        
        info = {
            "user_id": getattr(u, 'id', 'unknown'),
            "username": getattr(u, 'username', 'unknown'),
            "full_name": getattr(u, 'full_name', 'unknown'),
            "chat_id": getattr(c, 'id', 'unknown'),
            "chat_type": getattr(c, 'type', 'unknown'),
            "chat_title": getattr(c, 'title', None) or getattr(c, 'first_name', None) or "unknown",
            "chat_username": f"@{c.username}" if getattr(c, 'username', None) else "No Username",
            "chat_link": f"https://t.me/{c.username}" if getattr(c, 'username', None) else "No Link",
        }
        
        logger.info(
            f"📑 User info extracted: {info['full_name']} (@{info['username']}) "
            f"[ID: {info['user_id']}] in {info['chat_title']} [{info['chat_id']}] {info['chat_link']}"
        )
        return info
    except Exception as e:
        logger.error(f"❌ Error extracting user info: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            "user_id": "error",
            "username": "error",
            "full_name": "error",
            "chat_id": "error",
            "chat_type": "error",
            "chat_title": "error",
            "chat_username": "Error",
            "chat_link": "Error",
        }

def log_with_user_info(level: str, message: str, user_info: Dict[str, any]) -> None:
    """Log message with user information"""
    try:
        user_detail = (
            f"👤 {user_info['full_name']} (@{user_info['username']}) "
            f"[ID: {user_info['user_id']}] | "
            f"💬 {user_info['chat_title']} [{user_info['chat_id']}] "
            f"({user_info['chat_type']}) {user_info['chat_link']}"
        )
        full_message = f"{message} | {user_detail}"

        level_upper = level.upper()
        if level_upper == "INFO":
            logger.info(full_message)
        elif level_upper == "DEBUG":
            logger.debug(full_message)
        elif level_upper == "WARNING":
            logger.warning(full_message)
        elif level_upper == "ERROR":
            logger.error(full_message)
        else:
            logger.info(full_message)
    except Exception as e:
        logger.error(f"❌ Error in log_with_user_info: {str(e)}")

def error_handler_decorator(func):
    """Decorator to handle errors in handler functions"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            user_info = None
            if update and update.message:
                user_info = extract_user_info(update.message)
                log_with_user_info("INFO", f"🎯 Executing {func.__name__}", user_info)
            
            return await func(update, context)
        except TelegramError as e:
            error_msg = f"🔴 Telegram API error in {func.__name__}: {str(e)}"
            logger.error(error_msg)
            logger.error(f"Traceback: {traceback.format_exc()}")
            
            if user_info:
                log_with_user_info("ERROR", error_msg, user_info)
            
            try:
                if update and update.message:
                    await update.message.reply_text(
                        "❌ <b>Telegram API Error</b>\n\n"
                        "There was an issue communicating with Telegram. Please try again later.",
                        parse_mode='HTML'
                    )
            except Exception as nested_e:
                logger.error(f"❌ Failed to send error message: {str(nested_e)}")
        
        except Exception as e:
            error_msg = f"🔴 Unexpected error in {func.__name__}: {str(e)}"
            logger.error(error_msg)
            logger.error(f"Traceback: {traceback.format_exc()}")
            
            if user_info:
                log_with_user_info("ERROR", error_msg, user_info)
            
            try:
                if update and update.message:
                    await update.message.reply_text(
                        "❌ <b>Internal Error</b>\n\n"
                        "An unexpected error occurred. The error has been logged and will be investigated.",
                        parse_mode='HTML'
                    )
            except Exception as nested_e:
                logger.error(f"❌ Failed to send error message: {str(nested_e)}")
    
    return wrapper

# Supported languages configuration
SUPPORTED_LANGUAGES = {
    'python': {'ext': '.py', 'cmd': ['python3']},
    'javascript': {'ext': '.js', 'cmd': ['node']},
    'bash': {'ext': '.sh', 'cmd': ['bash']},
    'shell': {'ext': '.sh', 'cmd': ['bash']},
}

# Security restrictions
FORBIDDEN_PATTERNS = [
    r'import\s+os',
    r'import\s+subprocess',
    r'import\s+sys',
    r'__import__',
    r'eval\s*\(',
    r'exec\s*\(',
    r'open\s*\(',
    r'file\s*\(',
    r'input\s*\(',
    r'raw_input\s*\(',
    r'rm\s+-rf',
    r'sudo',
    r'chmod',
    r'chown',
    r'curl',
    r'wget',
    r'nc\s',
    r'netcat',
]

MAX_EXECUTION_TIME = 10  # seconds
MAX_OUTPUT_LENGTH = 4000  # characters
MAX_CODE_LENGTH = 10000  # characters

# HTTP SERVER FOR DEPLOYMENT
class DummyHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for keep-alive server"""

    def do_GET(self):
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Code evaluation bot is alive!")
        except Exception as e:
            logger.error(f"❌ HTTP server GET error: {str(e)}")

    def do_HEAD(self):
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
        except Exception as e:
            logger.error(f"❌ HTTP server HEAD error: {str(e)}")

    def log_message(self, format, *args):
        # Suppress HTTP server logs
        pass

def start_dummy_server() -> None:
    """Start dummy HTTP server for deployment platforms"""
    try:
        port = int(os.environ.get("PORT", 10000))
        server = HTTPServer(("0.0.0.0", port), DummyHandler)
        logger.info(f"🌐 Dummy server listening on port {port}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"❌ Failed to start HTTP server: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")

def is_code_safe(code: str) -> Tuple[bool, str]:
    """Check if code contains potentially dangerous patterns"""
    try:
        if not code or not isinstance(code, str):
            return False, "Invalid code input"
        
        if len(code) > MAX_CODE_LENGTH:
            return False, f"Code too long (max {MAX_CODE_LENGTH} characters)"
        
        for pattern in FORBIDDEN_PATTERNS:
            try:
                if re.search(pattern, code, re.IGNORECASE):
                    logger.warning(f"🚫 Forbidden pattern detected: {pattern}")
                    return False, f"Forbidden pattern detected: {pattern}"
            except re.error as e:
                logger.error(f"❌ Regex error with pattern {pattern}: {str(e)}")
                continue
        
        return True, ""
    except Exception as e:
        logger.error(f"❌ Error in security check: {str(e)}")
        return False, f"Security check failed: {str(e)}"

def cleanup_temp_file(file_path: str) -> None:
    """Safely cleanup temporary file"""
    try:
        if file_path and os.path.exists(file_path):
            os.unlink(file_path)
            logger.debug(f"🗑️ Cleaned up temp file: {file_path}")
    except OSError as e:
        logger.warning(f"⚠️ Failed to cleanup temp file {file_path}: {str(e)}")
    except Exception as e:
        logger.error(f"❌ Unexpected error cleaning up temp file {file_path}: {str(e)}")

async def kill_process_tree(pid: int) -> None:
    """Kill process and all its children"""
    try:
        if not psutil.pid_exists(pid):
            logger.debug(f"🔍 Process {pid} doesn't exist")
            return
        
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        
        # Terminate children first
        for child in children:
            try:
                child.terminate()
                logger.debug(f"🛑 Terminated child process {child.pid}")
            except psutil.NoSuchProcess:
                pass
            except Exception as e:
                logger.warning(f"⚠️ Error terminating child process {child.pid}: {str(e)}")
        
        # Wait for children to terminate
        gone, alive = psutil.wait_procs(children, timeout=3)
        
        # Kill remaining children
        for child in alive:
            try:
                child.kill()
                logger.debug(f"💀 Killed stubborn child process {child.pid}")
            except psutil.NoSuchProcess:
                pass
            except Exception as e:
                logger.warning(f"⚠️ Error killing child process {child.pid}: {str(e)}")
        
        # Terminate parent
        try:
            parent.terminate()
            parent.wait(timeout=3)
            logger.debug(f"🛑 Terminated parent process {pid}")
        except psutil.TimeoutExpired:
            parent.kill()
            logger.debug(f"💀 Killed parent process {pid}")
        except psutil.NoSuchProcess:
            pass
        except Exception as e:
            logger.warning(f"⚠️ Error terminating parent process {pid}: {str(e)}")
            
    except psutil.NoSuchProcess:
        logger.debug(f"🔍 Process {pid} no longer exists")
    except Exception as e:
        logger.error(f"❌ Error killing process tree {pid}: {str(e)}")

async def execute_code(code: str, language: str = 'python') -> Dict[str, Any]:
    """Execute code safely with timeout and resource limits"""
    temp_file_path = None
    process = None
    
    try:
        logger.info(f"🚀 Starting code execution - Language: {language}")
        
        # Validate language
        if not language or language not in SUPPORTED_LANGUAGES:
            error_msg = f"Unsupported language: {language}. Supported: {', '.join(SUPPORTED_LANGUAGES.keys())}"
            logger.warning(f"⚠️ {error_msg}")
            return {
                'success': False,
                'output': '',
                'error': error_msg
            }
        
        # Validate code
        if not code or not isinstance(code, str):
            error_msg = "Invalid code input"
            logger.warning(f"⚠️ {error_msg}")
            return {
                'success': False,
                'output': '',
                'error': error_msg
            }
        
        # Security check
        is_safe, reason = is_code_safe(code)
        if not is_safe:
            error_msg = f"Code rejected for security reasons: {reason}"
            logger.warning(f"🚫 {error_msg}")
            return {
                'success': False,
                'output': '',
                'error': error_msg
            }
        
        lang_config = SUPPORTED_LANGUAGES[language]
        logger.debug(f"🔧 Language config: {lang_config}")
        
        # Create temporary file with error handling
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', 
                suffix=lang_config['ext'], 
                delete=False
            ) as temp_file:
                temp_file.write(code)
                temp_file_path = temp_file.name
            
            logger.debug(f"📝 Created temp file: {temp_file_path}")
        except IOError as e:
            error_msg = f"Failed to create temporary file: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return {
                'success': False,
                'output': '',
                'error': error_msg
            }
        
        # Verify temp file was created
        if not os.path.exists(temp_file_path):
            error_msg = "Temporary file was not created"
            logger.error(f"❌ {error_msg}")
            return {
                'success': False,
                'output': '',
                'error': error_msg
            }
        
        # Execute code with comprehensive error handling
        try:
            logger.debug(f"⚡ Executing: {lang_config['cmd'] + [temp_file_path]}")
            
            process = await asyncio.create_subprocess_exec(
                *lang_config['cmd'], temp_file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=1024*1024,  # 1MB limit for stdout/stderr
                preexec_fn=os.setsid if hasattr(os, 'setsid') else None  # Create process group on Unix
            )
            
            logger.debug(f"🔄 Process started with PID: {process.pid}")
            
            try:
                # Wait for process completion with timeout
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=MAX_EXECUTION_TIME
                )
                
                logger.debug(f"✅ Process completed with return code: {process.returncode}")
                
                # Decode output with error handling
                try:
                    stdout_str = stdout.decode('utf-8', errors='replace')
                    stderr_str = stderr.decode('utf-8', errors='replace')
                except UnicodeDecodeError as e:
                    logger.warning(f"⚠️ Unicode decode error: {str(e)}")
                    stdout_str = str(stdout)
                    stderr_str = str(stderr)
                
                # Truncate output if too long
                if len(stdout_str) > MAX_OUTPUT_LENGTH:
                    stdout_str = stdout_str[:MAX_OUTPUT_LENGTH] + "\n... (output truncated)"
                    logger.debug("✂️ Output truncated due to length")
                
                if len(stderr_str) > MAX_OUTPUT_LENGTH:
                    stderr_str = stderr_str[:MAX_OUTPUT_LENGTH] + "\n... (error output truncated)"
                    logger.debug("✂️ Error output truncated due to length")
                
                success = process.returncode == 0
                output = stdout_str if success else stderr_str
                
                result = {
                    'success': success,
                    'output': output,
                    'error': stderr_str if not success else '',
                    'return_code': process.returncode
                }
                
                status = "✅ SUCCESS" if success else "❌ FAILED"
                logger.info(f"{status} - Return code: {process.returncode}")
                
                return result
                
            except asyncio.TimeoutError:
                logger.warning(f"⏰ Execution timeout after {MAX_EXECUTION_TIME} seconds")
                
                # Kill the process tree
                if process and process.pid:
                    await kill_process_tree(process.pid)
                
                try:
                    await process.wait()
                except Exception as e:
                    logger.warning(f"⚠️ Error waiting for process after timeout: {str(e)}")
                
                return {
                    'success': False,
                    'output': '',
                    'error': f"Execution timed out after {MAX_EXECUTION_TIME} seconds"
                }
            
        except FileNotFoundError as e:
            error_msg = f"Command not found: {lang_config['cmd'][0]}. Please ensure the interpreter is installed."
            logger.error(f"❌ {error_msg}")
            return {
                'success': False,
                'output': '',
                'error': error_msg
            }
        except PermissionError as e:
            error_msg = f"Permission denied executing code: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return {
                'success': False,
                'output': '',
                'error': error_msg
            }
        except OSError as e:
            error_msg = f"OS error during execution: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return {
                'success': False,
                'output': '',
                'error': error_msg
            }
        except Exception as e:
            error_msg = f"Unexpected error during execution: {str(e)}"
            logger.error(f"❌ {error_msg}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                'success': False,
                'output': '',
                'error': error_msg
            }
            
    except Exception as e:
        error_msg = f"Fatal error in code execution: {str(e)}"
        logger.error(f"💥 {error_msg}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            'success': False,
            'output': '',
            'error': error_msg
        }
    finally:
        # Always cleanup temp file
        if temp_file_path:
            cleanup_temp_file(temp_file_path)

@error_handler_decorator
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    logger.info("🎯 Processing /start command")
    
    welcome_message = """🤖 <b>Code Evaluation Bot</b>

Welcome! I can safely execute code in multiple languages with built-in security measures.

<b>Quick Commands:</b>
• <code>/eval python print("Hello!")</code>
• <code>?eval js console.log("Hi!")</code>  
• <code>!eval bash echo "Test"</code>

⚠️ <b>Secure execution with 10s timeout & output limits</b>"""
    
    # Create inline keyboard
    keyboard = [
        [
            InlineKeyboardButton("📢 Updates", url=UPDATES_CHANNEL),
            InlineKeyboardButton("💬 Support", url=SUPPORT_GROUP)
        ],
        [
            InlineKeyboardButton("➕ Add Me To Your Group", 
                               url=f"https://t.me/{BOT_USERNAME}?startgroup=true")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_message, 
        parse_mode='HTML', 
        reply_markup=reply_markup
    )

@error_handler_decorator
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    logger.info("🎯 Processing /help command")
    
    short_help = """🤖 <b>Code Evaluation Bot - Quick Help</b>

<b>Usage:</b> <code>/eval &lt;lang&gt; &lt;code&gt;</code> or <code>?eval &lt;lang&gt; &lt;code&gt;</code>

<b>Languages:</b> python, javascript, bash/shell

<b>Examples:</b>
<code>/eval python print("Hello!")</code>
<code>?eval js console.log("Hi!")</code>

<b>Security:</b> 10s timeout, output limits, no dangerous operations allowed."""
    
    # Create expand/minimize button
    keyboard = [[
        InlineKeyboardButton("📖 Expand Help", callback_data="help_expand")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        short_help, 
        parse_mode='HTML', 
        reply_markup=reply_markup
    )

async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle help expand/minimize callbacks"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "help_expand":
        expanded_help = """🤖 <b>Code Evaluation Bot - Detailed Help</b>

<b>Commands:</b> /eval, ?eval, !eval &lt;language&gt; &lt;code&gt;

<b>Languages:</b>
🐍 python - Python 3 interpreter
🟨 javascript - Node.js runtime  
🐚 bash/shell - Bash commands

<b>Examples:</b>
<code>/eval python
for i in range(3):
    print(f"Number: {i}")</code>

<b>Security & Limits:</b> 10s execution timeout, 4KB output limit, forbidden: file access, network, system commands."""
        
        keyboard = [[
            InlineKeyboardButton("📄 Minimize Help", callback_data="help_minimize")
        ]]
    else:  # help_minimize
        expanded_help = """🤖 <b>Code Evaluation Bot - Quick Help</b>

<b>Usage:</b> <code>/eval &lt;lang&gt; &lt;code&gt;</code> or <code>?eval &lt;lang&gt; &lt;code&gt;</code>

<b>Languages:</b> python, javascript, bash/shell

<b>Examples:</b>
<code>/eval python print("Hello!")</code>
<code>?eval js console.log("Hi!")</code>

<b>Security:</b> 10s timeout, output limits, no dangerous operations allowed."""
        
        keyboard = [[
            InlineKeyboardButton("📖 Expand Help", callback_data="help_expand")
        ]]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=expanded_help,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

@error_handler_decorator
async def langs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /langs command"""
    logger.info("🎯 Processing /langs command")
    
    langs_message = """<b>Supported Languages:</b>

🐍 <b>Python</b> (<code>python</code>)
- Python 3 interpreter
- Most standard library modules
- Examples: 
  <code>/eval python print("Hello!")</code>
  <code>?eval python print("Hello!")</code>
  <code>!eval python print("Hello!")</code>

🟨 <b>JavaScript</b> (<code>javascript</code>)  
- Node.js runtime
- Built-in modules available
- Examples:
  <code>/eval javascript console.log("Hello!")</code>
  <code>?eval javascript console.log("Hello!")</code>

🐚 <b>Bash</b> (<code>bash</code> or <code>shell</code>)
- Bash shell commands
- Common utilities available
- Examples:
  <code>/eval bash echo "Hello!"</code>
  <code>!eval bash echo "Hello!"</code>

⚠️ <b>Security restrictions apply to all languages</b>"""
    
    await update.message.reply_text(langs_message, parse_mode='HTML')

@error_handler_decorator
async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ping command"""
    logger.info("🎯 Processing /ping command")
    
    start_time = time.time()
    
    # Determine if we're in a group or private chat
    is_group = update.effective_chat.type in ['group', 'supergroup']
    
    # Send initial ping message
    if is_group:
        # In groups, reply to the original message
        ping_message = await update.message.reply_text("🛰️ Pinging...")
    else:
        # In private chats, send normally
        ping_message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🛰️ Pinging..."
        )
    
    # Calculate ping time
    end_time = time.time()
    ping_time = round((end_time - start_time) * 1000, 2)  # Convert to milliseconds
    
    # Edit message with pong response and hyperlink
    pong_text = f'🏓 <a href="https://t.me/SoulMeetsHQ">Pong!</a> {ping_time}ms'
    
    await context.bot.edit_message_text(
        chat_id=ping_message.chat.id,
        message_id=ping_message.message_id,
        text=pong_text,
        parse_mode='HTML',
        disable_web_page_preview=True
    )

def validate_eval_args(args: list, message_text: str) -> Tuple[bool, Optional[str], Optional[str], str]:
    """Validate and parse eval command arguments"""
    try:
        if not args:
            return False, None, None, "❌ <b>Usage:</b> <code>/eval &lt;language&gt; &lt;code&gt;</code>\n\n<b>Example:</b> <code>/eval python print('Hello, World!')</code>\nUse <code>/langs</code> to see supported languages."
        
        # Parse language and code
        if len(args) < 2:
            return False, None, None, "❌ Please provide both language and code.\n\n<b>Usage:</b> <code>/eval &lt;language&gt; &lt;code&gt;</code>"
        
        language = args[0].lower()
        code = ' '.join(args[1:])
        
        # Handle multiline code (from message text)
        if '\n' in message_text:
            lines = message_text.split('\n')
            if len(lines) > 1:
                # Extract code from multiline message
                first_line_parts = lines[0].split()
                if len(first_line_parts) >= 2:
                    language = first_line_parts[1].lower()
                    code = '\n'.join(lines[1:])
        
        if not code.strip():
            return False, None, None, "❌ No code provided to execute."
        
        return True, language, code, ""
    except Exception as e:
        logger.error(f"❌ Error validating eval args: {str(e)}")
        return False, None, None, f"❌ Error parsing command arguments: {str(e)}"

def escape_html(text: str) -> str:
    """Escape HTML entities in text"""
    try:
        if not text or not isinstance(text, str):
            return ""
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    except Exception as e:
        logger.error(f"❌ Error escaping HTML: {str(e)}")
        return str(text)

@error_handler_decorator
async def eval_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /eval command"""
    user_info = extract_user_info(update.message)
    log_with_user_info("INFO", "🎯 Processing /eval command", user_info)
    
    # Validate arguments
    is_valid, language, code, error_message = validate_eval_args(
        context.args or [], 
        update.message.text or ""
    )
    
    if not is_valid:
        await update.message.reply_text(error_message, parse_mode='HTML')
        return
    
    log_with_user_info("INFO", f"📝 Code execution requested - Language: {language}", user_info)
    
    # Show "typing" status
    try:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, 
            action='typing'
        )
    except Exception as e:
        logger.warning(f"⚠️ Failed to send typing action: {str(e)}")
    
    try:
        # Execute code
        result = await execute_code(code, language)
        
        # Format response
        if result['success']:
            response = f"✅ <b>Execution successful ({language})</b>\n\n"
            if result['output']:
                escaped_output = escape_html(result['output'])
                response += f"<b>Output:</b>\n<pre>{escaped_output}</pre>"
            else:
                response += "<i>(No output)</i>"
        else:
            response = f"❌ <b>Execution failed ({language})</b>\n\n"
            if result['error']:
                escaped_error = escape_html(result['error'])
                response += f"<b>Error:</b>\n<pre>{escaped_error}</pre>"
        
        # Add execution info
        if 'return_code' in result:
            response += f"\n\n<b>Return code:</b> <code>{result['return_code']}</code>"
        
        log_with_user_info("INFO", f"✅ Code execution completed - Success: {result['success']}", user_info)
        await update.message.reply_text(response, parse_mode='HTML')
        
    except Exception as e:
        error_msg = f"Internal error during code execution: {str(e)}"
        logger.error(f"❌ {error_msg}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        log_with_user_info("ERROR", error_msg, user_info)
        
        escaped_error = escape_html(str(e))
        await update.message.reply_text(
            f"❌ <b>Internal error occurred:</b>\n<pre>{escaped_error}</pre>",
            parse_mode='HTML'
        )

def parse_eval_message(message_text: str) -> Tuple[bool, Optional[str], Optional[str], str]:
    """Parse ?eval, !eval, ?ping, or !ping messages"""
    try:
        if not message_text or not isinstance(message_text, str):
            return False, None, None, "Invalid message"
        
        # Check if message starts with ?ping or !ping
        if message_text.startswith('?ping') or message_text.startswith('!ping'):
            return True, "ping", None, ""
        
        # Check if message starts with ?eval or !eval
        if not (message_text.startswith('?eval') or message_text.startswith('!eval')):
            return False, None, None, "Not an eval message"
        
        # Remove the prefix and process like /eval command
        content = message_text[5:].strip()  # Remove '?eval' or '!eval'
        
        if not content:
            return False, None, None, "❌ <b>Usage:</b> <code>?eval &lt;language&gt; &lt;code&gt;</code> or <code>!eval &lt;language&gt; &lt;code&gt;</code>\n\n<b>Example:</b> <code>?eval python print('Hello, World!')</code>\nUse <code>/langs</code> to see supported languages."
        
        # Parse language and code from content
        parts = content.split()
        if len(parts) < 2:
            return False, None, None, "❌ Please provide both language and code.\n\n<b>Usage:</b> <code>?eval &lt;language&gt; &lt;code&gt;</code> or <code>!eval &lt;language&gt; &lt;code&gt;</code>"
        
        language = parts[0].lower()
        code = ' '.join(parts[1:])
        
        # Handle multiline code
        if '\n' in message_text:
            lines = message_text.split('\n')
            if len(lines) > 1:
                # Extract code from multiline message
                first_line_parts = lines[0].split()
                if len(first_line_parts) >= 2:
                    language = first_line_parts[1].lower()
                    code = '\n'.join(lines[1:])
        
        if not code.strip():
            return False, None, None, "❌ No code provided to execute."
        
        return True, language, code, ""
    except Exception as e:
        logger.error(f"❌ Error parsing eval message: {str(e)}")
        return False, None, None, f"Error parsing message: {str(e)}"

@error_handler_decorator
async def handle_eval_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages that start with ?eval, !eval, ?ping, or !ping"""
    user_info = extract_user_info(update.message)
    message_text = update.message.text or ""
    
    try:
        # Parse the message
        is_valid, command_or_language, code, error_message = parse_eval_message(message_text)
        
        if not is_valid:
            # Not an eval/ping message, ignore silently
            return
        
        # Handle ping commands
        if command_or_language == "ping":
            log_with_user_info("INFO", "🏓 Processing ping message", user_info)
            await ping_command(update, context)
            return
        
        # Handle eval commands
        if error_message:
            await update.message.reply_text(error_message, parse_mode='HTML')
            return
        
        language = command_or_language
        log_with_user_info("INFO", f"📝 Eval message received - Language: {language}", user_info)
        
        # Show "typing" status
        try:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id, 
                action='typing'
            )
        except Exception as e:
            logger.warning(f"⚠️ Failed to send typing action: {str(e)}")
        
        # Execute code
        result = await execute_code(code, language)
        
        # Format response
        if result['success']:
            response = f"✅ <b>Execution successful ({language})</b>\n\n"
            if result['output']:
                escaped_output = escape_html(result['output'])
                response += f"<b>Output:</b>\n<pre>{escaped_output}</pre>"
            else:
                response += "<i>(No output)</i>"
        else:
            response = f"❌ <b>Execution failed ({language})</b>\n\n"
            if result['error']:
                escaped_error = escape_html(result['error'])
                response += f"<b>Error:</b>\n<pre>{escaped_error}</pre>"
        
        # Add execution info
        if 'return_code' in result:
            response += f"\n\n<b>Return code:</b> <code>{result['return_code']}</code>"
        
        log_with_user_info("INFO", f"✅ Eval message execution completed - Success: {result['success']}", user_info)
        await update.message.reply_text(response, parse_mode='HTML')
        
    except Exception as e:
        error_msg = f"Error handling eval message: {str(e)}"
        logger.error(f"❌ {error_msg}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        log_with_user_info("ERROR", error_msg, user_info)
        
        escaped_error = escape_html(str(e))
        await update.message.reply_text(
            f"❌ <b>Internal error occurred:</b>\n<pre>{escaped_error}</pre>",
            parse_mode='HTML'
        )

async def post_init(application):
    """Post initialization - setup bot commands menu"""
    try:
        logger.info("🚀 Setting up bot commands menu")
        
        commands = [
            BotCommand("start", "Welcome message and bot introduction"),
            BotCommand("help", "Show detailed help and usage examples"),
            BotCommand("eval", "Execute code in supported languages"),
            BotCommand("langs", "Show all supported programming languages"),
            BotCommand("ping", "Check bot response time"),
        ]
        
        await application.bot.set_my_commands(commands)
        logger.info("✅ Bot commands menu setup completed")
        
        # Log bot info
        try:
            bot_info = await application.bot.get_me()
            logger.info(f"🤖 Bot info: @{bot_info.username} ({bot_info.first_name}) - ID: {bot_info.id}")
        except Exception as e:
            logger.warning(f"⚠️ Could not get bot info: {str(e)}")
            
    except Exception as e:
        logger.error(f"❌ Error in post_init: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler for the application"""
    try:
        error = context.error
        logger.error(f"🔥 Global error handler triggered: {str(error)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Extract user info if available
        user_info = None
        if isinstance(update, Update) and update.message:
            try:
                user_info = extract_user_info(update.message)
                log_with_user_info("ERROR", f"Global error: {str(error)}", user_info)
            except Exception as e:
                logger.error(f"❌ Error extracting user info in error handler: {str(e)}")
        
        # Handle specific error types
        if isinstance(error, NetworkError):
            logger.error("🌐 Network error occurred")
            if isinstance(update, Update) and update.message:
                try:
                    await update.message.reply_text(
                        "❌ <b>Network Error</b>\n\nThere was a network connectivity issue. Please try again.",
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.error(f"❌ Failed to send network error message: {str(e)}")
        
        elif isinstance(error, TimedOut):
            logger.error("⏰ Request timed out")
            if isinstance(update, Update) and update.message:
                try:
                    await update.message.reply_text(
                        "❌ <b>Timeout Error</b>\n\nThe request timed out. Please try again.",
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.error(f"❌ Failed to send timeout error message: {str(e)}")
        
        elif isinstance(error, BadRequest):
            logger.error(f"📝 Bad request: {str(error)}")
            if isinstance(update, Update) and update.message:
                try:
                    await update.message.reply_text(
                        "❌ <b>Invalid Request</b>\n\nThe request was invalid. Please check your input.",
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.error(f"❌ Failed to send bad request error message: {str(e)}")
        
        elif isinstance(error, Forbidden):
            logger.error(f"🚫 Forbidden: {str(error)}")
            # Don't try to send a message if we're forbidden
        
        elif isinstance(error, ChatMigrated):
            logger.error(f"🔄 Chat migrated: {error.new_chat_id}")
            # Handle chat migration if needed
        
        else:
            logger.error(f"❓ Unhandled error type: {type(error).__name__}")
            if isinstance(update, Update) and update.message:
                try:
                    await update.message.reply_text(
                        "❌ <b>Unexpected Error</b>\n\nAn unexpected error occurred. The error has been logged.",
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.error(f"❌ Failed to send generic error message: {str(e)}")
    
    except Exception as e:
        logger.error(f"💥 Fatal error in global error handler: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")

def validate_environment() -> bool:
    """Validate that required dependencies are available"""
    try:
        logger.info("🔍 Validating environment dependencies")
        
        # Check Python version
        python_version = sys.version_info
        if python_version < (3, 7):
            logger.error(f"❌ Python 3.7+ required, found {python_version.major}.{python_version.minor}")
            return False
        else:
            logger.info(f"✅ Python version: {python_version.major}.{python_version.minor}.{python_version.micro}")
        
        # Check required modules
        required_modules = ['telegram', 'psutil', 'asyncio', 'tempfile', 'subprocess']
        for module in required_modules:
            try:
                __import__(module)
                logger.debug(f"✅ Module {module} available")
            except ImportError as e:
                logger.error(f"❌ Required module {module} not available: {str(e)}")
                return False
        
        # Check interpreters
        for lang, config in SUPPORTED_LANGUAGES.items():
            cmd = config['cmd'][0]
            try:
                result = subprocess.run([cmd, '--version'], 
                                      capture_output=True, 
                                      text=True, 
                                      timeout=5)
                if result.returncode == 0:
                    version_info = result.stdout.strip() or result.stderr.strip()
                    logger.info(f"✅ {lang} interpreter ({cmd}): {version_info.split()[0] if version_info else 'Available'}")
                else:
                    logger.warning(f"⚠️ {lang} interpreter ({cmd}) available but version check failed")
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError) as e:
                logger.warning(f"⚠️ {lang} interpreter ({cmd}) may not be available: {str(e)}")
        
        logger.info("✅ Environment validation completed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error during environment validation: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

def get_bot_token() -> Optional[str]:
    """Get bot token from environment or command line with proper error handling"""
    try:
        # Try environment variable first
        token = os.getenv('BOT_TOKEN')
        if token and token.strip():
            logger.info("✅ Bot token found in environment variable")
            return token.strip()
        
        # Try command line argument
        if len(sys.argv) > 1 and sys.argv[1].strip():
            logger.info("✅ Bot token found in command line arguments")
            return sys.argv[1].strip()
        
        return None
    except Exception as e:
        logger.error(f"❌ Error getting bot token: {str(e)}")
        return None

def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown"""
    def signal_handler(signum, frame):
        logger.info(f"🛑 Received signal {signum}, shutting down gracefully...")
        sys.exit(0)
    
    try:
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        logger.info("✅ Signal handlers setup completed")
    except Exception as e:
        logger.warning(f"⚠️ Could not setup signal handlers: {str(e)}")

def main():
    """Main function with comprehensive error handling"""
    try:
        logger.info("🚀 Starting Code Evaluation Bot")
        
        # Setup signal handlers
        setup_signal_handlers()
        
        # Validate environment
        if not validate_environment():
            logger.error("❌ Environment validation failed")
            sys.exit(1)
        
        # Get bot token
        token = get_bot_token()
        if not token:
            logger.error("❌ No bot token provided")
            print("\n" + "="*50)
            print("ERROR: No bot token provided!")
            print("="*50)
            print("Please provide bot token using one of these methods:")
            print("1. Set BOT_TOKEN environment variable:")
            print("   export BOT_TOKEN='your_token_here'")
            print("2. Pass token as command line argument:")
            print("   python bot.py YOUR_BOT_TOKEN")
            print("="*50 + "\n")
            sys.exit(1)
        
        # Validate token format
        if not re.match(r'^\d{8,10}:[a-zA-Z0-9_-]{35}$', token):
            logger.warning("⚠️ Bot token format appears invalid")
        
        logger.info("🔧 Creating application")
        
        # Create application with comprehensive configuration
        application = (
            Application.builder()
            .token(token)
            .post_init(post_init)
            .connect_timeout(30.0)
            .read_timeout(30.0)
            .write_timeout(30.0)
            .pool_timeout(30.0)
            .build()
        )
        
        # Add command handlers with error handling
        logger.info("📋 Adding command handlers")
        
        handlers = [
            ("start", start_command),
            ("help", help_command),
            ("eval", eval_command),
            ("langs", langs_command),
            ("ping", ping_command),
        ]
        
        for command, handler in handlers:
            try:
                application.add_handler(CommandHandler(command, handler))
                logger.debug(f"✅ Added handler for /{command}")
            except Exception as e:
                logger.error(f"❌ Failed to add handler for /{command}: {str(e)}")
        
        # Add callback query handler for help expand/minimize
        try:
            application.add_handler(CallbackQueryHandler(help_callback, pattern="^help_"))
            logger.debug("✅ Added callback query handler for help")
        except Exception as e:
            logger.error(f"❌ Failed to add callback query handler: {str(e)}")
        
        # Add message handler for ?eval, !eval, ?ping, and !ping
        try:
            application.add_handler(MessageHandler(
                filters.TEXT & ~filters.COMMAND, 
                handle_eval_message
            ))
            logger.debug("✅ Added message handler for eval messages")
        except Exception as e:
            logger.error(f"❌ Failed to add message handler: {str(e)}")
        
        # Add global error handler
        try:
            application.add_error_handler(global_error_handler)
            logger.debug("✅ Added global error handler")
        except Exception as e:
            logger.error(f"❌ Failed to add error handler: {str(e)}")
        
        # Start dummy HTTP server for deployment platforms
        try:
            threading.Thread(target=start_dummy_server, daemon=True).start()
        except Exception as e:
            logger.error(f"❌ Failed to start HTTP server: {str(e)}")
        
        logger.info("🎉 Bot setup completed, starting polling...")
        
        # Run the application
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user (Ctrl+C)")
        sys.exit(0)
    except Exception as e:
        logger.error(f"💥 Fatal error in main: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        print(f"\n❌ FATAL ERROR: {str(e)}")
        print("Check the logs above for more details.")
        sys.exit(1)

if __name__ == '__main__':
    main()
