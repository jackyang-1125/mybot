import datetime
import asyncio
import os
import threading
from flask import Flask, render_template_string
import discord
from discord import app_commands
from discord.ext import commands, tasks

# ==================== 1. 設置 Flask 網頁伺服器 (解決 Render Port 問題並提供 HTML 彈出式視窗) ====================
app = Flask(__name__)

# 記憶體資料庫
exams_data = [
    {
        "id": 1,
        "date": "2026-09-14",
        "period": "第1節",
        "content": "國文<br>張美涵",
    }
]

# 專屬論壇 / 討論串 ID
EXCLUSIVE_CHANNEL_ID = 1548647622263181342
dashboard_message_id = None

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <title>班級互動式課表</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #313338; color: #dbdee1; padding: 20px; margin: 0; }
        h2 { text-align: center; color: #fff; }
        .table-container { overflow-x: auto; background: #2b2d31; padding: 15px; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.3); }
        table { width: 100%; border-collapse: collapse; text-align: center; font-size: 14px; }
        th, td { border: 1px solid #3f4147; padding: 10px; vertical-align: middle; }
        th { background: #1e1f22; color: #f2f3f5; }
        tr:nth-child(even) { background: #2b2d31; }
        tr:nth-child(odd) { background: #313338; }
        .empty { color: #80848e; }
        .sat-disabled { background: #232428 !important; color: #555; }
    </style>
</head>
<body>
    <h2>📅 班級互動式課表</h2>
    <div class="table-container">
        <table>
            <thead>
                <tr>
                    <th>節次</th>
                    <th>時間</th>
                    <th>一</th>
                    <th>二</th>
                    <th>三</th>
                    <th>四</th>
                    <th>五</th>
                    <th>六</th>
                </tr>
            </thead>
            <tbody>
                {% for period_name, time_str in time_slots %}
                <tr>
                    <td><strong>{{ period_name }}</strong></td>
                    <td>{{ time_str }}</td>
                    {% for i in range(6) %}
                        {% if i == 5 and loop.index0 > 4 %}
                            <td class="sat-disabled">-</td>
                        {% else %}
                            <td>
                                {% set found = namespace(content='') %}
                                {%- for item in exams_data -%}
                                    {%- if item.period == period_name -%}
                                        {{ found.content | safe }}
                                    {%- endif -%}
                                {%- endfor -%}
                                {% if not found.content %}<span class="empty">-</span>{% endif %}
                            </td>
                        {% endif %}
                    {% endfor %}
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</body>
</html>
"""


@app.route("/")
def index():
  time_slots = [
      ("第0節早自修", "07:30 - 08:00"),
      ("第1節", "08:10 - 08:55"),
      ("第2節", "09:15 - 10:00"),
      ("第3節", "10:10 - 10:55"),
      ("第4節", "11:05 - 11:50"),
      ("第5節", "13:10 - 13:55"),
      ("第6節", "14:10 - 14:55"),
      ("第7節", "15:10 - 15:55"),
      ("第8節", "16:05 - 16:50"),
      ("第9節", "16:55 - 17:40"),
      ("第10節", "17:45 - 18:30"),
  ]
  return render_template_string(
      HTML_TEMPLATE, time_slots=time_slots, exams_data=exams_data
  )


def run_flask():
  port = int(os.environ.get("PORT", 10000))
  app.run(host="0.0.0.0", port=port)


# ==================== 2. Discord 機器人核心 ====================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
dashboard_message_id = None


@bot.event
async def on_ready():
  print(f"Discord 機器人已成功登入 --> {bot.user}")
  try:
    synced = await bot.tree.sync()
    print(f"已同步 {len(synced)} 個 Slash 指令")
  except Exception as e:
    print(e)
  daily_exam_reminder.start()


@tasks.loop(hours=24)
async def daily_exam_reminder():
  now_taiwan = datetime.datetime.now(
      datetime.timezone(datetime.timedelta(hours=8))
  )
  tomorrow = (now_taiwan + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

  for exam in exams_data:
    if exam["date"] == tomorrow:
      channel = bot.get_channel(EXCLUSIVE_CHANNEL_ID)
      if channel:
        embed = discord.Embed(
            title="📢 課程時間提醒",
            description=(
                f"明天 (**{tomorrow}**) 的排程：\n⏰ **{exam['period']}**\n📌"
                f" **{exam['content']}**"
            ),
            color=0xFF5733,
        )
        await channel.send(content="@everyone", embed=embed)


@daily_exam_reminder.before_loop
async def before_reminder():
  await bot.wait_until_ready()


def create_dashboard_view():
  # 取得 Render 部署網址（請確保將 YOUR_RENDER_URL 換成你實際的網址或透過環境變數傳入）
  web_url = os.environ.get(
      "RENDER_External_URL", "https://mybot-xxxx.onrender.com"
  )
  view = discord.ui.View(timeout=None)
  view.add_item(
      discord.ui.Button(
          label="🌐 開啟互動式 HTML 課表",
          style=discord.ButtonStyle.link,
          url=web_url,
      )
  )
  return view


def create_dashboard_embed():
  now_taiwan = datetime.datetime.now(
      datetime.timezone(datetime.timedelta(hours=8))
  )
  embed = discord.Embed(
      title="📅 班級課表與時間總表",
      description=(
          "點擊下方按鈕即可開啟**彈出式 HTML 互動網頁課表**（支援手機與電腦版"
          "內嵌檢視）！\n\n➕ 新增指令：`/add_schedule` | 🗑️ 刪除指令：`/del_schedule`"
      ),
      color=0x3498DB,
      timestamp=now_taiwan,
  )
  embed.set_footer(text="動態 HTML 課表系統")
  return embed


async def update_or_create_dashboard(channel):
  global dashboard_message_id
  embed = create_dashboard_embed()
  view = create_dashboard_view()

  if dashboard_message_id:
    try:
      msg = await channel.fetch_message(dashboard_message_id)
      await msg.edit(embed=embed, view=view)
      return
    except discord.NotFound:
      pass

  msg = await channel.send(embed=embed, view=view)
  dashboard_message_id = msg.id


def in_exclusive_channel():
  async def predicate(interaction: discord.Interaction):
    channel = interaction.channel
    is_valid = False
    if interaction.channel_id == EXCLUSIVE_CHANNEL_ID:
      is_valid = True
    elif (
        isinstance(channel, discord.Thread)
        and channel.parent_id == EXCLUSIVE_CHANNEL_ID
    ):
      is_valid = True

    if not is_valid:
      await interaction.response.send_message(
          f"❌ 此指令只能在專屬版面 <#{EXCLUSIVE_CHANNEL_ID}> 中使用！",
          ephemeral=True,
      )
      return False
    return True

  return app_commands.check(predicate)


@bot.tree.command(name="add_schedule", description="[專屬版面] 在課表中填入內容")
@app_commands.describe(
    date="日期 (格式：YYYY-MM-DD)", period="選擇節次", content="要填入的內容"
)
@app_commands.choices(
    period=[
        app_commands.Choice(
            name="第0節早自修 (07:30-08:00)", value="第0節早自修"
        ),
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
    ]
)
@in_exclusive_channel()
async def slash_add_schedule(
    interaction: discord.Interaction,
    date: str,
    period: str,
    content: str,
):
  new_id = max([e["id"] for e in exams_data], default=0) + 1
  new_exam = {"id": new_id, "date": date, "period": period, "content": content}
  exams_data.append(new_exam)

  target_channel = (
      interaction.channel
      if isinstance(interaction.channel, discord.Thread)
      else bot.get_channel(EXCLUSIVE_CHANNEL_ID)
  )
  if target_channel:
    await update_or_create_dashboard(target_channel)

  await interaction.response.send_message(
      f"✅ 成功填入課表 (ID: {new_id})：`{date}` | `{period}`", ephemeral=True
  )


@bot.tree.command(name="del_schedule", description="[專屬版面] 透過項目 ID 刪除內容")
@app_commands.describe(schedule_id="要刪除的項目 ID")
@in_exclusive_channel()
async def slash_del_schedule(
    interaction: discord.Interaction, schedule_id: int
):
  global exams_data
  initial_len = len(exams_data)
  exams_data = [e for e in exams_data if e["id"] != schedule_id]

  if len(exams_data) < initial_len:
    target_channel = (
        interaction.channel
        if isinstance(interaction.channel, discord.Thread)
        else bot.get_channel(EXCLUSIVE_CHANNEL_ID)
    )
    if target_channel:
      await update_or_create_dashboard(target_channel)
    await interaction.response.send_message(
        f"🗑️ 已成功刪除 ID 為 #{schedule_id} 的項目！", ephemeral=True
    )
  else:
    await interaction.response.send_message(
        f"❌ 找不到 ID 為 #{schedule_id} 的項目。", ephemeral=True
    )


@bot.tree.command(name="init_dashboard", description="[專屬版面] 生成課表面板")
@in_exclusive_channel()
async def slash_init_dashboard(interaction: discord.Interaction):
  target_channel = interaction.channel
  await update_or_create_dashboard(target_channel)
  await interaction.response.send_message(
      "✅ 互動式 HTML 課表面板已成功生成！", ephemeral=True
  )


if __name__ == "__main__":
  # 同時啟動 Flask 網頁伺服器與 Discord 機器人
  threading.Thread(target=run_flask, daemon=True).start()
  token = os.environ.get("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE")
  bot.run(token)
