# TS SMM PANEL BOT

## Install
```bash
pip install -r requirements.txt
```

## Setup
1. `.env.example` কপি করে `.env` নাম দিন।
2. নতুন Bot Token, Admin ID ও Provider API তথ্য বসান।
3. চালান:
```bash
python bot.py
```

## গুরুত্বপূর্ণ
- প্রকাশিত পুরোনো Bot Token ও Provider API Key revoke/regenerate করুন।
- Provider service ID আপনার provider panel-এর আসল ID হতে হবে।
- TON amount এই package-এ সরাসরি wallet balance unit হিসেবে যোগ হয়; TON→BDT conversion দরকার হলে আলাদা conversion logic যোগ করুন।
- Bot admin approve/reject-এ duplicate credit protection আছে।
