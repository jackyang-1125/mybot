import datetime
import asyncio
import os
import discord
from discord import app_commands
from discord.ext import commands, tasks

# 初始化 Discord 機器人
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 記憶體資料庫（格式：日期、節次、你自己輸入的內容）
# 例如: {"id": 1, "date": "2026-09-14", "period": "第1節", "content": "國文\n張美涵"}
exams_data = [
    {
        "id": 1,
        "date": "2026-09-14",
        "period": "第1節",
        "content": "國文\n張美涵",
    }
]

# 專屬論壇 / 討論串 ID
EXCLUSIVE_CHANNEL_ID = 1548647622263181342

dashboard_message_id = None
current_week_offset = 0  # 0 = 本週, +1 = 下一週, -1 = 上一週


@bot.event
async def on_ready():
  print(f"Discord 機器人已成功登入 --> {bot.user}")
  try:
    synced = await bot.tree.sync()
    print(f"已同步 {len(synced)} 個 Slash 指令")
  except Exception as e:
    print(e)
  daily_exam_reminder.start()


# 背景任務：每天檢查提醒並 @everyone
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
            title="📢 課程/時間排程提醒",
            description=(
                f"明天 (**{tomorrow}**) 的排程項目：\n"
                f"⏰ **{exam['period']}**\n"
                f"📝 **{exam['content']}**"
            ),
            color=0xFF5733,
        )
        await channel.send(content="@everyone", embed=embed)


@daily_exam_reminder.before_loop
async def before_reminder():
  await bot.wait_until_ready()


def get_target_week_range(offset):
  now_taiwan = datetime.datetime.now(
      datetime.timezone(datetime.timedelta(hours=8))
  )
  start_of_term = datetime.datetime(
      now_taiwan.year, 9, 1, tzinfo=datetime.timezone(datetime.timedelta(hours=8))
  )
  base_date = now_taiwan + datetime.timedelta(weeks=offset)

  delta_days = (base_date - start_of_term).days
  week_num = max(1, (delta_days // 7) + 1)

  # 取得週一到週六的日期
  start_of_week = base_date - datetime.timedelta(days=base_date.weekday())  # 週一
  days = [start_of_week + datetime.timedelta(days=i) for i in range(6)]  # 週一至週六

  return week_num, days


def create_dashboard_embed(week_offset):
  week_num, days = get_target_week_range(week_offset)
  now_taiwan = datetime.datetime.now(
      datetime.timezone(datetime.timedelta(hours=8))
  )

  # 對應截圖中的時間表結構
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

  # 建立對應當週每一天日期的對照表 (YYYY-MM-DD -> 星期幾)
  day_date_map = {}
  headers = ["節次", "時間"]
  weekdays_name = ["一", "二", "三", "四", "五", "六"]

  for i, d in enumerate(days):
    date_str = d.strftime("%Y-%m-%d")
    day_date_map[i] = date_str
    headers.append(f"{weekdays_name[i]}<br>({d.strftime('%m/%d')})")

  # 用 Markdown 模擬真實 HTML 表格排版
  table_lines = []
  table_lines.append(
      "| " + " | ".join(["節次", "時間", "一", "二", "三", "四", "五", "六"]) + " |"
  )
  table_lines.append("|" + "---|---|" + "---|---|" * 3)

  for period_name, time_str in time_slots:
    row = [period_name, time_str]
    for i in range(6):
      target_date = day_date_map[i]
      # 尋找該日期與該節次的資料
      matched = [
          e
          for e in exams_data
          if e["date"] == target_date and e["period"] == period_name
      ]
      if matched:
        # 顯示內容與 ID
        content_str = matched[0]["content"].replace("\n", "<br>")
        row.append(f"{content_str}<br>*(ID:{matched[0]['id']})*")
      else:
        row.append("-")
    table_lines.append("| " + " | ".join(row) + " |")

  table_markdown = "\n".join(table_lines)

  embed = discord.Embed(
      title=f"📅 班級課表與時間總表 (第 {week_num} 週)",
      description=(
          f"📊 **HTML 模擬表格檢視**\n{table_markdown}\n\n"
          "💡 使用下方按鈕切換 **上一週 / 下一週**\n"
          "➕ 新增指令：`/add_schedule` | 🗑️ 刪除指令：`/del_schedule`"
      ),
      color=0x3498DB,
      timestamp=now_taiwan,
  )
  embed.set_footer(text=f"系統自動換週 • 當前顯示第 {week_num} 週")
  return embed


class DashboardView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label="◀️ 上一週",
      style=discord.ButtonStyle.secondary,
      custom_id="prev_week",
  )
  async def prev_week_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    global current_week_offset
    current_week_offset -= 1
    await interaction.response.edit_message(
        embed=create_dashboard_embed(current_week_offset), view=self
    )

  @discord.ui.button(
      label="🔄 重新整理",
      style=discord.ButtonStyle.primary,
      custom_id="refresh_dashboard",
  )
  async def refresh_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.edit_message(
        embed=create_dashboard_embed(current_week_offset), view=self
    )

  @discord.ui.button(
      label="下一週 ▶️",
      style=discord.ButtonStyle.secondary,
      custom_id="next_week",
  )
  async def next_week_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    global current_week_offset
    current_week_offset += 1
    await interaction.response.edit_message(
        embed=create_dashboard_embed(current_week_offset), view=self
    )


async def update_or_create_dashboard(channel):
  global dashboard_message_id, current_week_offset
  embed = create_dashboard_embed(current_week_offset)
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
    date="日期 (格式：YYYY-MM-DD)",
    period="選擇節次 (例如：第0節早自修、第1節至第10節)",
    content="要填入的內容（例如：國文\n張美涵）",
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


@bot.tree.command(name="del_schedule", description="[專屬版面] 透過項目 ID 刪除填入的內容")
@app_commands.describe(schedule_id="要刪除的項目 ID (可從表格內看到)")
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
        f"❌ 找不到 ID 為 #{schedule_id} 的項目，請確認編號。", ephemeral=True
    )


@bot.tree.command(name="init_dashboard", description="[專屬版面] 生成或重置課表總表面板")
@in_exclusive_channel()
async def slash_init_dashboard(interaction: discord.Interaction):
  target_channel = interaction.channel
  await update_or_create_dashboard(target_channel)
  await interaction.response.send_message(
      "✅ 課表總表面板已成功生成！", ephemeral=True
  )


if __name__ == "__main__":
  token = os.environ.get("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE")
  bot.run(token)
