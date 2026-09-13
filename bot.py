import asyncio
import datetime
import os
import threading
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import discord
from discord.ext import commands, tasks

app = Flask(__name__)
app.config["SECRET_KEY"] = "secret!"
socketio = SocketIO(app, cors_allowed_origins="*")

exams_data = [
    {
        "id": 1,
        "date": "2026-09-15",
        "period": "第1節",
        "subject": "國文",
        "note": "第一冊全",
    }
]
forum_posts = [
    {
        "author": "系統公告",
        "content": "歡迎使用 Discord 聯絡簿與考試排程系統！",
        "time": "2026-09-13 19:30",
    }
]

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

DISCORD_CHANNEL_ID = 123456789012345678  # 請換成你的頻道 ID


@bot.event
async def on_ready():
  print(f"Discord 機器人已登入 --> {bot.user}")
  try:
    synced = await bot.tree.sync()
    print(f"已同步 {len(synced)} 個 Slash 指令")
  except Exception as e:
    print(e)
  daily_exam_reminder.start()


@tasks.loop(hours=24)
async def daily_exam_reminder():
  now_taiwan = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
  tomorrow = (now_taiwan + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
  for exam in exams_data:
    if exam["date"] == tomorrow:
      channel = bot.get_channel(DISCORD_CHANNEL_ID)
      if channel:
        embed = discord.Embed(
            title="📢 考試前一天提醒",
            description=f"明天 (**{tomorrow}**) 有考試，請做好準備！",
            color=0xFF5733,
        )
        embed.add_field(name="節次", value=exam["period"], inline=True)
        embed.add_field(name="科目", value=exam["subject"], inline=True)
        embed.add_field(name="備註/範圍", value=exam["note"], inline=False)
        await channel.send(embed=embed)


@daily_exam_reminder.before_loop
async def before_reminder():
  await bot.wait_until_ready()


@bot.tree.command(name="add_exam", description="新增考試排程")
@discord.app.commands.describe(
    date="日期 (YYYY-MM-DD)",
    period="節次",
    subject="科目",
    note="備註",
)
async def slash_add_exam(
    interaction: discord.Interaction,
    date: str,
    period: str,
    subject: str,
    note: str,
):
  new_exam = {
      "id": len(exams_data) + 1,
      "date": date,
      "period": period,
      "subject": subject,
      "note": note,
  }
  exams_data.append(new_exam)
  socketio.emit("update_exams", exams_data)
  await interaction.response.send_message(
      f"✅ 成功新增考試！\n> 日期：{date} | 科目：**{subject}**"
  )


@bot.tree.command(name="list_exams", description="查看所有考試排程")
async def slash_list_exams(interaction: discord.Interaction):
  if not exams_data:
    await interaction.response.send_message("目前沒有考試排程。")
    return
  embed = discord.Embed(title="📋 目前考試排程列表", color=0x3498DB)
  for exam in exams_data:
    embed.add_field(
        name=f"{exam['date']} ({exam['period']})",
        value=f"科目：**{exam['subject']}**\n範圍：{exam['note']}",
        inline=False,
    )
  await interaction.response.send_message(embed=embed)


@bot.tree.command(name="forum_post", description="在論壇發布討論")
@discord.app.commands.describe(content="想說的話")
async def slash_forum_post(interaction: discord.Interaction, content: str):
  time_str = (
      datetime.datetime.utcnow() + datetime.timedelta(hours=8)
  ).strftime("%Y-%m-%d %H:%M")
  new_post = {
      "author": interaction.user.name,
      "content": content,
      "time": time_str,
  }
  forum_posts.insert(0, new_post)
  socketio.emit("update_posts", forum_posts)
  await interaction.response.send_message(f"💬 成功發布貼文！\n> {content}")


@app.route("/")
def index():
  return render_template("index.html")


@socketio.on("connect")
def handle_connect():
  emit("update_data", {"exams": exams_data, "posts": forum_posts})


@socketio.on("add_exam")
def handle_add_exam(data):
  new_exam = {
      "id": len(exams_data) + 1,
      "date": data["date"],
      "period": data["period"],
      "subject": data["subject"],
      "note": data["note"],
  }
  exams_data.append(new_exam)
  socketio.emit("update_exams", exams_data)


@socketio.on("new_post")
def handle_new_post(data):
  forum_posts.insert(0, data)
  socketio.emit("update_posts", forum_posts)


def run_flask():
  port = int(os.environ.get("PORT", 5000))
  socketio.run(app, host="0.0.0.0", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
  flask_thread = threading.Thread(target=run_flask)
  flask_thread.start()
  # 從環境變數讀取 Token，或者直接填入你的 Bot Token
  bot.run(os.environ.get("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE"))
