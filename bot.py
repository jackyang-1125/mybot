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

# 記憶體資料庫（儲存純時間排程項目）
exams_data = [
    {
        "id": 1,
        "date": "2026-09-15",
        "period": "第0節早自修 (07:30-08:00)",
        "content": "範例時間項目",
    }
]

# 專屬論壇 / 討論串 ID
EXCLUSIVE_CHANNEL_ID = 1548647622263181342

dashboard_message_id = None
# 記錄目前面板顯示的週次偏移量（0 = 本週，+1 = 下一週，-1 = 上一週）
current_week_offset = 0


@bot.event
async def on_ready():
  print(f"Discord 機器人已成功登入 --> {bot.user}")
  try:
    synced = await bot.tree.sync()
    print(f"已同步 {len(synced)} 個 Slash 指令")
  except Exception as e:
    print(e)
  daily_exam_reminder.start()


# 背景任務：每天檢查一次提醒並 @everyone
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
            title="📢 時間排程提醒",
            description=(
                f"明天 (**{tomorrow}**) 有安排時間項目：\n"
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
  # 計算本週一與週日
  start_of_term = datetime.datetime(
      now_taiwan.year, 9, 1, tzinfo=datetime.timezone(datetime.timedelta(hours=8))
  )
  base_date = now_taiwan + datetime.timedelta(weeks=offset)

  # 計算學年度第幾週
  delta_days = (base_date - start_of_term).days
  week_num = max(1, (delta_days // 7) + 1)

  # 取得該週的星期一與星期日日期範圍
  start_of_week = base_date - datetime.timedelta(days=base_date.weekday())
  end_of_week = start_of_week + datetime.timedelta(days=6)

  return week_num, start_of_week.date(), end_of_week.date()


def create_dashboard_embed(week_offset):
  week_num, start_date, end_date = get_target_week_range(week_offset)
  now_taiwan = datetime.datetime.now(
      datetime.timezone(datetime.timedelta(hours=8))
  )

  embed = discord.Embed(
      title=f"📅 班級時間排程總表 (第 {week_num} 週)",
      description=(
          f"🗓️ **日期區間：{start_date} ~ {end_date}**\n"
          "💻 **[HTML 式排版檢視]**\n"
          "使用下方按鈕切換上一週 / 下一週，或使用指令新增/刪除。"
      ),
      color=0x2ECC71,
      timestamp=now_taiwan,
  )

  # 篩選屬於該週的項目
  filtered_exams = []
  for exam in exams_data:
    try:
      exam_date = datetime.datetime.strptime(exam["date"], "%Y-%m-%d").date()
      if start_date <= exam_date <= end_date:
        filtered_exams.append(exam)
    except ValueError:
      pass

  if not filtered_exams:
    embed.add_field(
        name="目前狀態",
        value=f"🎉 第 {week_num} 週目前沒有任何時間排程！",
        inline=False,
    )
  else:
    sorted_exams = sorted(
        filtered_exams, key=lambda x: (x["date"], x["period"])
    )
    for index, exam in enumerate(sorted_exams, 1):
      table_row = (
          f"┌─────────────────────────\n"
          f"│ ID: #{exam['id']} | 日期: {exam['date']}\n"
          f"│ ⏰ 時間: {exam['period']}\n"
          f"│ 📌 內容: {exam['content']}\n"
          f"└─────────────────────────"
      )
      embed.add_field(
          name=f"項目 #{index}", value=f"```yaml\n{table_row}\n```", inline=False
      )

  embed.set_footer(
      text=f"自動換週系統 • 偏移量: {week_offset} 週 (第 {week_num} 週)"
  )
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


@bot.tree.command(
    name="add_schedule", description="[專屬版面] 新增純時間排程項目"
)
@app_commands.describe(
    date="日期 (格式：YYYY-MM-DD)",
    period="時間/節次 (例如：第0節早自修 07:30-08:00)",
    content="行程說明或備註",
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
      f"✅ 成功新增排程 (ID: {new_id})：`{date}` | `{period}`", ephemeral=True
  )


@bot.tree.command(
    name="del_schedule", description="[專屬版面] 透過項目 ID 刪除排程"
)
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
        f"🗑️ 已成功刪除 ID 為 #{schedule_id} 的排程！", ephemeral=True
    )
  else:
    await interaction.response.send_message(
        f"❌ 找不到 ID 為 #{schedule_id} 的項目，請確認編號。", ephemeral=True
    )


@bot.tree.command(
    name="init_dashboard", description="[專屬版面] 生成或重置時間排程面板"
)
@in_exclusive_channel()
async def slash_init_dashboard(interaction: discord.Interaction):
  target_channel = interaction.channel
  await update_or_create_dashboard(target_channel)
  await interaction.response.send_message(
      "✅ 時間排程總表面板已成功生成！", ephemeral=True
  )


if __name__ == "__main__":
  token = os.environ.get("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE")
  bot.run(token)
