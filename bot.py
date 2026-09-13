import datetime
import asyncio
import os
import threading
from flask import Flask, render_template_string
import discord
from discord import app_commands
from discord.ext import commands

# ==================== 1. 設置 Flask 網頁伺服器 (純黑畫面) ====================
app = Flask(__name__)

exams_data = []         # 儲存單次排程與考試
recurring_tasks = []    # 儲存重複任務
EXCLUSIVE_CHANNEL_ID = 1548647622263181342
dashboard_message_id = None

BLACK_SCREEN_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <title>已關閉</title>
    <style>
        body { background-color: #000000; color: #555555; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; font-family: monospace; }
    </style>
</head>
<body>
    <div>[系統提示] 網頁版功能已停用，請直接在 Discord 頻道中查看課表與動態面板。</div>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(BLACK_SCREEN_TEMPLATE)

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# ==================== 2. Discord 機器人核心 ====================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Discord 機器人已成功登入 --> {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"已同步 {len(synced)} 個 Slash 指令")
    except Exception as e:
        print(e)


def clean_expired_schedules():
    """自動清除日期已經過去的單次排程"""
    global exams_data
    now_taiwan_date = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).date()
    
    valid_exams = []
    for item in exams_data:
        try:
            item_date = datetime.datetime.strptime(item["date"], "%Y-%m-%d").date()
            # 如果排程日期大於或等於今天，則保留
            if item_date >= now_taiwan_date:
                valid_exams.append(item)
        except ValueError:
            continue
    exams_data = valid_exams


class DashboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔔 立即提醒測試", style=discord.ButtonStyle.primary, custom_id="btn_test_reminder", row=0)
    async def test_reminder_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 測試訊息改成直接 @ 觸發的使用者
        await interaction.response.send_message(f"🔔 {interaction.user.mention} **[系統提醒測試]** 這是一則手動觸發的課表與考試提醒測試通知！", ephemeral=False)


def create_dashboard_embed():
    # 每次生成面板前先自動過濾掉過期的單次排程
    clean_expired_schedules()
    
    now_taiwan = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    embed = discord.Embed(
        title="📅 班級動態課表與排程總表",
        description="以下為目前最新的課程排程、考試與重複任務清單。已自動清除過期項目。",
        color=0x3498DB,
        timestamp=now_taiwan
    )
    
    # 1. 顯示一般考試與排程
    if not exams_data:
        embed.add_field(name="📋 單次排程與考試清單", value="📭 目前尚無單次排程內容。", inline=False)
    else:
        content_summary = ""
        for item in exams_data:
            content_summary += f"🔹 **ID #{item['id']}** | 📅 `{item['date']}` | ⏰ **{item['period']}**\n> {item['content']}\n\n"
        embed.add_field(name="📋 單次排程與考試清單", value=content_summary[:1024], inline=False)

    # 2. 顯示重複任務清單
    if not recurring_tasks:
        embed.add_field(name="🔄 重複任務與提醒清單", value="📭 目前尚無設定重複任務。", inline=False)
    else:
        rec_summary = ""
        for item in recurring_tasks:
            rec_summary += f"🔄 **ID R#{item['id']}** | 🔁 **頻率：{item['frequency']}** | ⏰ **{item['time']}**\n> {item['content']}\n\n"
        embed.add_field(name="🔄 重複任務與提醒清單", value=rec_summary[:1024], inline=False)

    embed.set_footer(text="Discord 官方排程與動態整合系統 | 自動清除過期事項")
    return embed


async def update_or_create_dashboard(channel):
    global dashboard_message_id
    embed = create_dashboard_embed()
    view = DashboardView()
    
    if dashboard_message_id:
        try:
            msg = await channel.fetch_message(dashboard_message_id)
            await msg.edit(embed=embed, view=view)
            return
        except discord.NotFound:
            pass
            
    msg = await channel.send(embed=embed, view=view)
    dashboard_message_id = msg.id


def is_admin():
    async def predicate(interaction: discord.Interaction):
        # 僅檢查是否為伺服器管理員或擁有者
        is_server_admin = interaction.user.guild_permissions.administrator or interaction.user == interaction.guild.owner
        if not is_server_admin:
            await interaction.response.send_message("❌ 只有伺服器管理員（版主）才能執行此指令！", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)


def in_exclusive_channel():
    async def predicate(interaction: discord.Interaction):
        channel = interaction.channel
        is_valid = False
        if interaction.channel_id == EXCLUSIVE_CHANNEL_ID:
            is_valid = True
        elif isinstance(channel, discord.Thread) and channel.parent_id == EXCLUSIVE_CHANNEL_ID:
            is_valid = True
            
        if not is_valid:
            await interaction.response.send_message(f"❌ 此指令只能在專屬版面 <#{EXCLUSIVE_CHANNEL_ID}> 中使用！", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)


# ==================== 3. 機器人指令區 ====================

@bot.tree.command(name="add_schedule", description="[版主專用] 在課表中填入考試或排程")
@app_commands.describe(date="日期 (格式：YYYY-MM-DD)", period="選擇節次", content="要填入的內容")
@app_commands.choices(period=[
    app_commands.Choice(name="第0節早自修 (07:30-08:00)", value="第0節早自修"),
    app_commands.Choice(name="第1節 (08:10-08:55)", value="第1節"),
    app_commands.Choice(name="第2節 (09:15-10:00)", value="第2節"),
    app_commands.Choice(name="第3節 (10:10-10:55)", value="第3節"),
    app_commands.Choice(name="第4節 (11:05-11:50)", value="第4節"),
    app_commands.Choice(name="第5節 (13:10-13:55)", value="第5節"),
    app_commands.Choice(name="第6節 (14:10-14:55)", value="第6節"),
    app_commands.Choice(name="第7節 (15:10-15:55)", value="第7節"),
    app_commands.Choice(name="第8節 (16:05-16:50)", value="第8節"),
    app_commands.Choice(name="第9節 (16:55-17:40)", value="第9節"),
    app_commands.Choice(name="第10節 (17:45-18:30)", value="第10節"),
])
@is_admin()
@in_exclusive_channel()
async def slash_add_schedule(interaction: discord.Interaction, date: str, period: str, content: str):
    try:
        input_date_obj = datetime.datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        await interaction.response.send_message("❌ 日期格式錯誤，請使用 `YYYY-MM-DD`（例如 `2026-09-14`）。", ephemeral=True)
        return

    # 檢查輸入的日期是否已經過期
    now_taiwan_date = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).date()
    if input_date_obj < now_taiwan_date:
        await interaction.response.send_message("❌ 無法新增已經過期的日期排程！", ephemeral=True)
        return

    new_id = max([e["id"] for e in exams_data], default=0) + 1
    new_exam = {"id": new_id, "date": date, "period": period, "content": content}
    exams_data.append(new_exam)

    target_channel = interaction.channel if isinstance(interaction.channel, discord.Thread) else bot.get_channel(EXCLUSIVE_CHANNEL_ID)
    if target_channel:
        await update_or_create_dashboard(target_channel)

    await interaction.response.send_message(f"✅ 成功新增排程 (ID: #{new_id})，並已同步更新至課表面板！", ephemeral=True)


@bot.tree.command(name="add_recurring", description="[版主專用] 新增重複性任務或提醒（例如每日、每週）")
@app_commands.describe(frequency="選擇重複頻率", time="執行時間 (格式 HH:MM，例如 07:30)", content="重複任務內容")
@app_commands.choices(frequency=[
    app_commands.Choice(name="每日重複 (Daily)", value="每日重複"),
    app_commands.Choice(name="每週重複 (Weekly)", value="每週重複"),
])
@is_admin()
@in_exclusive_channel()
async def slash_add_recurring(interaction: discord.Interaction, frequency: str, time: str, content: str):
    new_id = max([r["id"] for r in recurring_tasks], default=0) + 1
    new_task = {"id": new_id, "frequency": frequency, "time": time, "content": content}
    recurring_tasks.append(new_task)

    target_channel = interaction.channel if isinstance(interaction.channel, discord.Thread) else bot.get_channel(EXCLUSIVE_CHANNEL_ID)
    if target_channel:
        await update_or_create_dashboard(target_channel)

    await interaction.response.send_message(f"🔄 成功新增重複任務 (ID: R#{new_id})，已即時列在課表面板下方！", ephemeral=True)


@bot.tree.command(name="del_schedule", description="[版主專用] 透過項目 ID 刪除單次排程")
@app_commands.describe(schedule_id="要刪除的單次項目 ID")
@is_admin()
@in_exclusive_channel()
async def slash_del_schedule(interaction: discord.Interaction, schedule_id: int):
    global exams_data
    initial_len = len(exams_data)
    exams_data = [e for e in exams_data if e["id"] != schedule_id]

    if len(exams_data) < initial_len:
        target_channel = interaction.channel if isinstance(interaction.channel, discord.Thread) else bot.get_channel(EXCLUSIVE_CHANNEL_ID)
        if target_channel:
            await update_or_create_dashboard(target_channel)
        await interaction.response.send_message(f"🗑️ 已成功刪除單次項目 #{schedule_id}！", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ 找不到 ID 為 #{schedule_id} 的單次項目。", ephemeral=True)


@bot.tree.command(name="del_recurring", description="[版主專用] 透過任務 ID 刪除重複任務")
@app_commands.describe(recurring_id="要刪除的重複任務 ID (數字)")
@is_admin()
@in_exclusive_channel()
async def slash_del_recurring(interaction: discord.Interaction, recurring_id: int):
    global recurring_tasks
    initial_len = len(recurring_tasks)
    recurring_tasks = [r for r in recurring_tasks if r["id"] != recurring_id]

    if len(recurring_tasks) < initial_len:
        target_channel = interaction.channel if isinstance(interaction.channel, discord.Thread) else bot.get_channel(EXCLUSIVE_CHANNEL_ID)
        if target_channel:
            await update_or_create_dashboard(target_channel)
        await interaction.response.send_message(f"🗑️ 已成功刪除重複任務 R#{recurring_id}！", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ 找不到 ID 為 R#{recurring_id} 的重複任務。", ephemeral=True)


@bot.tree.command(name="init_dashboard", description="[版主專用] 在此頻道生成或刷新動態課表面板")
@is_admin()
@in_exclusive_channel()
async def slash_init_dashboard(interaction: discord.Interaction):
    target_channel = interaction.channel
    await update_or_create_dashboard(target_channel)
    await interaction.response.send_message("✅ 班級動態課表與重複任務面板已成功在此頻道生成！", ephemeral=True)


if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    token = os.environ.get("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE")
    bot.run(token)
