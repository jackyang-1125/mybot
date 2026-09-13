import datetime
import os
import discord
from discord.ext import commands, tasks

# 初始化 Discord 機器人
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 記憶體資料庫（儲存考試排程）
exams_data = [
    {
        "id": 1,
        "date": "2026-09-15",
        "period": "第1節",
        "subject": "國文",
        "note": "第一冊全",
    }
]

# 請填入你的 Discord 頻道 ID（用來發送考試提醒）
DISCORD_CHANNEL_ID = 123456789012345678


@bot.event
async def on_ready():
  print(f"Discord 機器人已成功登入 --> {bot.user}")
  try:
    synced = await bot.tree.sync()
    print(f"已同步 {len(synced)} 個 Slash 指令")
  except Exception as e:
    print(e)
  daily_exam_reminder.start()


# 背景任務：每天檢查一次，如果在明天有登記考試，就在前一天發送提醒
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


# --- Discord 伺服器斜線指令 ---


# 指令 1：新增考試排程
@bot.tree.command(name="add_exam", description="在伺服器中新增考試排程")
@discord.app.commands.describe(
    date="考試日期 (格式：YYYY-MM-DD)",
    period="節次 (例如：第零節早自修 / 第1節)",
    subject="考試科目",
    note="備註或考試範圍",
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

  embed = discord.Embed(
      title="✅ 成功新增考試排程", color=0x2ECC71, timestamp=datetime.datetime.now()
  )
  embed.add_field(name="日期", value=date, inline=True)
  embed.add_field(name="節次", value=period, inline=True)
  embed.add_field(name="科目", value=subject, inline=True)
  embed.add_field(name="範圍/備註", value=note, inline=False)
  embed.set_footer(text=f"建立者：{interaction.user.name}")

  await interaction.response.send_message(embed=embed)


# 指令 2：查看所有考試排程
@bot.tree.command(name="list_exams", description="查看目前所有的考試排程列表")
async def slash_list_exams(interaction: discord.Interaction):
  if not exams_data:
    await interaction.response.send_message(
        "目前伺服器中沒有任何考試排程。"
    )
    return

  embed = discord.Embed(title="📋 目前考試排程列表", color=0x3498DB)
  for exam in exams_data:
    embed.add_field(
        name=f"{exam['date']} ({exam['period']})",
        value=f"科目：**{exam['subject']}**\n範圍：{exam['note']}",
        inline=False,
    )
  await interaction.response.send_message(embed=embed)


# 啟動機器人
if __name__ == "__main__":
  token = os.environ.get("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE")
  bot.run(token)
