import os
import json
import logging
import sqlite3
from datetime import datetime, date
from telegram import Update, ParseMode
from telegram.ext import Updater, CommandHandler, CallbackContext, MessageHandler, Filters

# ==============================================
# 配置部分
# ==============================================

def load_config():
    """加载配置文件"""
    config_path = 'config.json'
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件 {config_path} 不存在")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    return config

# 加载配置
try:
    config = load_config()
    TOKEN = config.get('TELEGRAM_BOT_TOKEN')
    if not TOKEN:
        raise ValueError("配置文件中缺少 TELEGRAM_BOT_TOKEN")
except Exception as e:
    print(f"加载配置文件失败: {e}")
    # 如果配置文件加载失败，可以在这里设置一个默认值用于测试
    # 但实际部署时不应该这样做
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', None)
    if not TOKEN:
        raise ValueError("无法从配置文件或环境变量中获取TELEGRAM_BOT_TOKEN")

# ==============================================
# 日志设置
# ==============================================

# 启用日志
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==============================================
# 数据库初始化
# ==============================================

def init_db():
    """初始化数据库"""
    conn = sqlite3.connect('data/checkin_bot.db')
    cursor = conn.cursor()
    
    # 用户表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 签到记录表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS checkins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        checkin_date DATE,
        points INTEGER DEFAULT 1,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("数据库初始化完成")

# 确保数据库存在
if not os.path.exists('data'):
    os.makedirs('data')
init_db()

# ==============================================
# 功能函数
# ==============================================

def start(update: Update, context: CallbackContext) -> None:
    """发送欢迎消息"""
    user = update.effective_user
    update.message.reply_text(
        f"你好 {user.first_name}!\n"
        "我是签到机器人，使用 /checkin 每日签到获取积分。\n"
        "管理员可以使用 /stats 查看所有用户签到记录。"
    )

def checkin(update: Update, context: CallbackContext) -> None:
    """处理用户签到"""
    user = update.effective_user
    user_id = user.id
    today = date.today().isoformat()
    
    conn = sqlite3.connect('data/checkin_bot.db')
    cursor = conn.cursor()
    
    # 检查用户是否存在，不存在则添加
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (user_id, username, first_name, last_name) VALUES (?, ?, ?, ?)",
            (user_id, user.username, user.first_name, user.last_name)
        )
        conn.commit()
        logger.info(f"新用户 {user_id} 已添加到数据库")
    
    # 检查今天是否已签到
    cursor.execute("SELECT * FROM checkins WHERE user_id = ? AND checkin_date = ?", (user_id, today))
    if cursor.fetchone():
        update.message.reply_text("今天已经签到过了，明天再来吧！")
    else:
        # 记录签到
        cursor.execute(
            "INSERT INTO checkins (user_id, checkin_date) VALUES (?, ?)",
            (user_id, today)
        )
        conn.commit()
        update.message.reply_text("签到成功！获得1积分。")
        logger.info(f"用户 {user_id} 签到成功")
    
    conn.close()

def stats(update: Update, context: CallbackContext) -> None:
    """管理员查看签到统计"""
    user = update.effective_user
    if user.id not in get_admin_ids():
        update.message.reply_text("您没有权限使用此命令。")
        return
    
    conn = sqlite3.connect('data/checkin_bot.db')
    cursor = conn.cursor()
    
    # 获取所有用户及其签到次数
    cursor.execute("""
        SELECT u.user_id, u.username, u.first_name, u.last_name, COUNT(c.id) as checkin_count
        FROM users u
        LEFT JOIN checkins c ON u.user_id = c.user_id
        GROUP BY u.user_id
        ORDER BY checkin_count DESC
    """)
    results = cursor.fetchall()
    
    if not results:
        update.message.reply_text("暂无签到记录。")
        conn.close()
        return
    
    # 构建回复消息
    message = "📊 签到统计:\n\n"
    for row in results:
        user_id, username, first_name, last_name, count = row
        name = f"{first_name} {last_name}" if last_name else first_name
        username_display = f"@{username}" if username else "无用户名"
        message += f"{name} ({username_display}) - 签到次数: {count}\n"
    
    # 添加总签到次数
    cursor.execute("SELECT COUNT(*) FROM checkins")
    total_checkins = cursor.fetchone()[0]
    message += f"\n总签到次数: {total_checkins}"
    
    # 分割消息，避免超过Telegram消息长度限制
    max_length = 4000
    messages = [message[i:i+max_length] for i in range(0, len(message), max_length)]
    
    for msg in messages:
        update.message.reply_text(msg)
    
    conn.close()

def get_admin_ids() -> list:
    """从配置文件中获取管理员ID列表"""
    return config.get('ADMIN_IDS', [])

# ==============================================
# 主程序
# ==============================================

def error_handler(update: Update, context: CallbackContext) -> None:
    """记录错误并通知用户"""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    
    if update.effective_message:
        update.effective_message.reply_text("抱歉，处理您的请求时出现了错误。")

def main() -> None:
    """启动机器人"""
    # 创建Updater并传递bot的token
    updater = Updater(TOKEN)
    
    # 获取dispatcher来注册handler
    dispatcher = updater.dispatcher
    
    # 注册命令处理程序
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("checkin", checkin))
    dispatcher.add_handler(CommandHandler("stats", stats))
    
    # 注册错误处理程序
    dispatcher.add_error_handler(error_handler)
    
    # 启动机器人
    logger.info("签到机器人已启动，正在轮询更新...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()