# Discord Staff Bot

بوت لإدارة فريق الإدارة في السيرفر مع أنظمة: التوظيف، الترقية، التقييم، الإجازات، الحضور، الإحصائيات، والـ Logs.

## التشغيل

1. ثبّت المتطلبات:

```bash
pip install -r requirements.txt
```

2. أنشئ ملف `.env`:

```env
DISCORD_TOKEN=YOUR_TOKEN
GUILD_ID=123456789012345678
LOG_CHANNEL_NAME=bot-logs
STAFF_MANAGER_ROLE=Staff Manager
```

3. شغّل البوت:

```bash
python bot.py
```

## الأوامر

- `!توظيف @user`
- `!ترقية @user`
- `!تنزيل @user`
- `!ترقية-فئة @user`
- `!فصل @user`
- `!اجازة @user <hours>`
- `!تسجيل`
- `!خروج`
- `!say <message>`
- `/stats`
- `/love @user`
- `/rate @staff`

## ملاحظات

- كل البيانات محفوظة في ملفات JSON داخل `data/`.
- يجب أن تكون الرتب مطابقة للأسماء المعرّفة في `bot.py`.
