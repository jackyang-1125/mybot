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

# 專屬論壇 / 討論串 ID
EXCLUSIVE_CHANNEL_ID = 1548647622263181342

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


# 背景任務：每天檢查一次考試提醒，並 @everyone 通知大家
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
            title="📢 考試前一天提醒",
            description=f"明天 (**{tomorrow}**) 有考試，請做好準備！",
            color=0xFF5733,
        )
        embed.add_field(name="節次", value=exam["period"], inline=True)
        embed.add_field(name="科目", value=exam["subject"], inline=True)
        embed.add_field(name="備註/範圍", value=exam["note"], inline=False)
        await channel.send(content="@everyone", embed=embed)


@daily_exam_reminder.before_loop
async def before_reminder():
  await bot.wait_until_ready()


def create_dashboard_embed():
  embed = discord.Embed(
      title="📊 班級即時考試排程總表",
      description=(
          "以下為目前所有登記的考試清單。\n"
          "當有人使用 `/add_exam` 新增時，此表格會**即時自動更新**！"
      ),
      color=0x3498DB,
      timestamp=datetime.datetime.now(),
  )

  if not exams_data:
    embed.add_field(
        name="目前狀態", value="🎉 目前沒有任何排程中的考試！", inline=False
    )
  else:
    sorted_exams = sorted(exams_data, key=lambda x: x["date"])
    for index, exam in enumerate(sorted_exams, 1):
      embed.add_field(
          name=f"#{index} 📅 {exam['date']} ({exam['period']})",
          value=f"科目：**{exam['subject']}**\n範圍/備註：{exam['note']}",
          inline=False,
      )

  embed.set_footer(text="由 Discord 考試排程機器人即時同步")
  return embed


class DashboardView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label="🔄 重新整理表格",
      style=discord.ButtonStyle.primary,
      custom_id="refresh_dashboard",
  )
  async def refresh_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.edit_message(
        embed=create_dashboard_embed(), view=self
    )


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
    name="add_exam", description="[專屬版面] 在伺服器中新增考試排程"
)
@app_commands.describe(
    date="考試日期 (格式：YYYY-MM-DD)",
    period="節次 (例如：第零節早自修 / 第1節)",
    subject="考試科目",
    note="備註或考試範圍",
)
@in_exclusive_channel()
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

  target_channel = (
      interaction.channel
      if isinstance(interaction.channel, discord.Thread)
      else bot.get_channel(EXCLUSIVE_CHANNEL_ID)
  )
  if target_channel:
    await update_or_create_dashboard(target_channel)

  await interaction.response.send_message(
      f"✅ 成功新增考試：{date} ({period}) {subject}！總表已即時更新。",
      ephemeral=True,
  )


@bot.tree.command(
    name="init_dashboard",
    description="[專屬版面] 在此頻道生成或重置即時考試表格面板",
)
@in_exclusive_channel()
async def slash_init_dashboard(interaction: discord.Interaction):
  target_channel = interaction.channel
  await update_or_create_dashboard(target_channel)
  await interaction.response.send_message(
      "✅ 即時考試排程表格面板已成功生成！", ephemeral=True
  )


if __name__ == "__main__":
  token = os.environ.get("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE")
  bot.run(token)
