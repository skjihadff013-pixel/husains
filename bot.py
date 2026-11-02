#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sqlite3, logging, asyncio
from datetime import datetime
from dotenv import load_dotenv
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

load_dotenv()
BOT_TOKEN=os.getenv("BOT_TOKEN","")
ADMIN_IDS={int(x) for x in os.getenv("ADMIN_IDS","").split(",") if x.strip()}
PROVIDER_API_URL=os.getenv("PROVIDER_API_URL","")
PROVIDER_API_KEY=os.getenv("PROVIDER_API_KEY","")
BKASH_NUMBER=os.getenv("BKASH_NUMBER","")
TON_WALLET_ADDRESS=os.getenv("TON_WALLET_ADDRESS","")
SUPPORT_USERNAME=os.getenv("SUPPORT_USERNAME","")
ORDER_CHANNEL=os.getenv("ORDER_CHANNEL","") or None
REFERRAL_BONUS=float(os.getenv("REFERRAL_BONUS","1"))
DB_PATH=os.getenv("DB_PATH","smm_panel.db")
logging.basicConfig(level=logging.INFO)
log=logging.getLogger("4x-smm")
states={}

DEFAULT_SERVICES=[
("Telegram","1K Lifetime Members","17156",100,100,100000),
("Telegram","1K Views","14759",1,100,1000000),
("Telegram","1K Reactions + Views","15644",10,50,200000),
("Facebook","1K Followers (Lifetime)","19534",60,100,100000),
("Facebook","1K Reactions","7329",30,100,5000000),
("Facebook","1K Views","9766",4,100,5000000),
("TikTok","1K Views","15050",7,100,1000000),
("TikTok","1K Likes","16934",10,10,100000),
("Instagram","1K Followers (Lifetime)","13393",90,100,1000000),
("Instagram","1K Likes","19263",20,100,100000),
("Instagram","1K Views","18808",2,100,1000000),
("YouTube","1K Views","9589",200,100,1000000),
("YouTube","1K Likes","19519",30,100,100000),
("YouTube","1K Subscribers","8427",70,100,2000)]

def conn():
    c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON"); return c

def init_db():
    c=conn()
    c.executescript("""CREATE TABLE IF NOT EXISTS users(
      user_id INTEGER PRIMARY KEY,name TEXT,username TEXT,balance REAL DEFAULT 0,
      referred_by INTEGER,refer_count INTEGER DEFAULT 0,joined_at TEXT);
    CREATE TABLE IF NOT EXISTS services(
      service_id INTEGER PRIMARY KEY AUTOINCREMENT,category TEXT,name TEXT,
      provider_service_id TEXT,rate REAL,min_qty INTEGER,max_qty INTEGER,
      UNIQUE(category,name));
    CREATE TABLE IF NOT EXISTS orders(
      order_id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,service_id INTEGER,
      service_name TEXT,link TEXT,qty INTEGER,price REAL,provider_order_id TEXT,
      status TEXT,created_at TEXT);
    CREATE TABLE IF NOT EXISTS deposits(
      deposit_id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,amount REAL,
      method TEXT,status TEXT DEFAULT 'pending',photo_id TEXT,created_at TEXT,
      approved_at TEXT);
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);""")
    n=c.execute("SELECT COUNT(*) n FROM services").fetchone()["n"]
    if not n: c.executemany("INSERT OR IGNORE INTO services(category,name,provider_service_id,rate,min_qty,max_qty) VALUES(?,?,?,?,?,?)",DEFAULT_SERVICES)
    c.commit(); c.close()

def admin(uid): return uid in ADMIN_IDS
def now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def main_kb(uid):
    rows=[["🛒 New Order","📦 My Orders"],["💰 Balance","➕ Add Funds"],["👤 My Profile","👥 Refer & Earn"],["📞 Support","💲 Price List"]]
    if admin(uid): rows.append(["👑 Admin Panel"])
    return ReplyKeyboardMarkup(rows,resize_keyboard=True)
def admin_kb(): return ReplyKeyboardMarkup([["➕ Add Service","🗑️ Delete Service"],["📊 Stats","📢 Broadcast"],["⬅️ Main Menu"]],resize_keyboard=True)
def back(): return ReplyKeyboardMarkup([["⬅️ Main Menu"]],resize_keyboard=True)

async def api(payload):
    if not PROVIDER_API_URL or not PROVIDER_API_KEY: return {"error":"Provider API is not configured"}
    payload={**payload,"key":PROVIDER_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=20) as x:
            r=await x.post(PROVIDER_API_URL,data=payload); r.raise_for_status()
            return r.json()
    except Exception as e: return {"error":str(e)}

def ensure_user(u, ref=None):
    c=conn(); row=c.execute("SELECT user_id FROM users WHERE user_id=?",(u.id,)).fetchone()
    if not row:
        c.execute("INSERT INTO users(user_id,name,username,referred_by,joined_at) VALUES(?,?,?,?,?)",(u.id,u.first_name,u.username,ref,now()))
        if ref and ref!=u.id: c.execute("UPDATE users SET refer_count=refer_count+1 WHERE user_id=?",(ref,))
    else: c.execute("UPDATE users SET name=?,username=? WHERE user_id=?",(u.first_name,u.username,u.id))
    c.commit(); c.close()

async def start(update, context):
    ref=None
    if context.args and context.args[0].startswith("ref_"):
        try: ref=int(context.args[0][4:])
        except: pass
    ensure_user(update.effective_user,ref)
    c=conn(); bal=c.execute("SELECT balance FROM users WHERE user_id=?",(update.effective_user.id,)).fetchone()["balance"]; c.close()
    await update.message.reply_text(f"👋 স্বাগতম, {update.effective_user.first_name}!\n💰 Balance: ৳{bal:.2f}\n\nনিচের মেনু থেকে নির্বাচন করুন 👇",reply_markup=main_kb(update.effective_user.id))

async def text_router(update,context):
    uid=update.effective_user.id; t=update.message.text.strip(); ensure_user(update.effective_user)
    if uid in states: return await state_flow(update,context)
    if t=="🛒 New Order":
        c=conn(); cats=[r["category"] for r in c.execute("SELECT DISTINCT category FROM services ORDER BY category")]; c.close()
        states[uid]={"s":"cat"}; await update.message.reply_text("📂 Category নির্বাচন করুন:",reply_markup=ReplyKeyboardMarkup([cats[i:i+2] for i in range(0,len(cats),2)]+[["⬅️ Main Menu"]],resize_keyboard=True))
    elif t=="📦 My Orders":
        c=conn(); rows=c.execute("SELECT * FROM orders WHERE user_id=? ORDER BY order_id DESC LIMIT 10",(uid,)).fetchall(); c.close()
        if not rows: return await update.message.reply_text("📦 কোনো অর্ডার নেই।")
        for r in rows:
            kb=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh",callback_data=f"status:{r['order_id']}")]]) if r["provider_order_id"] else None
            await update.message.reply_text(f"🆔 Order #{r['order_id']}\n📦 {r['service_name']}\n📊 Qty: {r['qty']}\n💰 Charge: ৳{r['price']:.2f}\n📌 Status: {r['status']}",reply_markup=kb)
    elif t=="💰 Balance":
        c=conn(); b=c.execute("SELECT balance FROM users WHERE user_id=?",(uid,)).fetchone()["balance"]; c.close(); await update.message.reply_text(f"💰 আপনার Balance: ৳{b:.2f}")
    elif t=="➕ Add Funds":
        states[uid]={"s":"method"}; await update.message.reply_text("পেমেন্ট মেথড নির্বাচন করুন:",reply_markup=ReplyKeyboardMarkup([["📲 bKash","💎 TON"],["⬅️ Main Menu"]],resize_keyboard=True))
    elif t=="👤 My Profile":
        c=conn(); u=c.execute("SELECT * FROM users WHERE user_id=?",(uid,)).fetchone(); n,spent=c.execute("SELECT COUNT(*),COALESCE(SUM(price),0) FROM orders WHERE user_id=?",(uid,)).fetchone(); c.close()
        await update.message.reply_text(f"👤 Profile\n🆔 ID: {uid}\n💰 Balance: ৳{u['balance']:.2f}\n🛒 Orders: {n}\n💸 Spent: ৳{spent:.2f}\n👥 Referrals: {u['refer_count']}")
    elif t=="👥 Refer & Earn":
        me=await context.bot.get_me(); link=f"https://t.me/{me.username}?start=ref_{uid}"
        await update.message.reply_text(f"👥 Refer & Earn\n\n🔗 আপনার Referral Link:\n{link}\n\nপ্রতিটি referral-এর approved deposit-এ ৳{REFERRAL_BONUS:.2f} bonus।")
    elif t=="💲 Price List":
        c=conn(); rows=c.execute("SELECT * FROM services ORDER BY category,name").fetchall(); c.close(); out="💲 Price List (per 1000)\n"; last=""
        for r in rows:
            if r["category"]!=last: out+=f"\n📂 {r['category']}\n"; last=r["category"]
            out+=f"• {r['name']} — ৳{r['rate']:.2f}\n"
        await update.message.reply_text(out)
    elif t=="📞 Support":
        if SUPPORT_USERNAME: await update.message.reply_text("📞 Support:",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Message Support",url=f"https://t.me/{SUPPORT_USERNAME.lstrip('@')}")]]))
        else: await update.message.reply_text("📞 Support এখন সেট করা নেই।")
    elif t=="👑 Admin Panel" and admin(uid): await update.message.reply_text("👑 Admin Panel",reply_markup=admin_kb())
    elif t=="📊 Stats" and admin(uid):
        c=conn(); u=c.execute("SELECT COUNT(*) FROM users").fetchone()[0]; o,rev=c.execute("SELECT COUNT(*),COALESCE(SUM(price),0) FROM orders WHERE status!='failed'").fetchone(); p=c.execute("SELECT COUNT(*) FROM deposits WHERE status='pending'").fetchone()[0]; c.close()
        await update.message.reply_text(f"📊 Stats\n👥 Users: {u}\n🛒 Orders: {o}\n💰 Revenue: ৳{rev:.2f}\n⏳ Pending deposits: {p}")
    elif t=="➕ Add Service" and admin(uid):
        states[uid]={"s":"addsvc"}; await update.message.reply_text("এক লাইনে লিখুন:\nCategory,Name,ProviderID,Rate,Min,Max",reply_markup=back())
    elif t=="🗑️ Delete Service" and admin(uid):
        c=conn(); rows=c.execute("SELECT * FROM services ORDER BY category,name").fetchall(); c.close()
        await update.message.reply_text("যেটি delete করবেন চাপুন:",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"❌ {r['category']} — {r['name']}",callback_data=f"del:{r['service_id']}")] for r in rows]))
    elif t=="📢 Broadcast" and admin(uid):
        states[uid]={"s":"broadcast"}; await update.message.reply_text("Broadcast message পাঠান:",reply_markup=back())
    elif t=="⬅️ Main Menu": await update.message.reply_text("🏠 Main Menu",reply_markup=main_kb(uid))

async def state_flow(update,context):
    uid=update.effective_user.id; t=update.message.text.strip(); st=states[uid]
    if t=="⬅️ Main Menu": states.pop(uid,None); return await update.message.reply_text("🏠 Main Menu",reply_markup=main_kb(uid))
    if st["s"]=="cat":
        c=conn(); rows=c.execute("SELECT * FROM services WHERE category=? ORDER BY name",(t,)).fetchall(); c.close()
        if not rows: return await update.message.reply_text("❌ সঠিক category নির্বাচন করুন।")
        st.update(s="svc",cat=t); await update.message.reply_text("🛍️ Service নির্বাচন করুন:",reply_markup=ReplyKeyboardMarkup([[r["name"]] for r in rows]+[["⬅️ Main Menu"]],resize_keyboard=True))
    elif st["s"]=="svc":
        c=conn(); r=c.execute("SELECT * FROM services WHERE category=? AND name=?",(st["cat"],t)).fetchone(); c.close()
        if not r:return await update.message.reply_text("❌ Service button চাপুন।")
        st.update(s="link",svc=dict(r)); await update.message.reply_text(f"🔗 Link পাঠান:\n📦 {r['name']}",reply_markup=back())
    elif st["s"]=="link":
        if not (t.startswith("http://") or t.startswith("https://") or t.startswith("@")): return await update.message.reply_text("❌ সঠিক link/username পাঠান।")
        st.update(s="qty",link=t); r=st["svc"]; await update.message.reply_text(f"🔢 Quantity দিন (min {r['min_qty']}, max {r['max_qty']}):")
    elif st["s"]=="qty":
        try:q=int(t)
        except:return await update.message.reply_text("❌ শুধু সংখ্যা দিন।")
        r=st["svc"]
        if not r["min_qty"]<=q<=r["max_qty"]: return await update.message.reply_text(f"❌ Quantity {r['min_qty']} থেকে {r['max_qty']} হতে হবে।")
        price=round(q*r["rate"]/1000,2); c=conn(); bal=c.execute("SELECT balance FROM users WHERE user_id=?",(uid,)).fetchone()["balance"]
        if bal<price:c.close(); states.pop(uid,None); return await update.message.reply_text(f"❌ Balance কম। প্রয়োজন ৳{price:.2f}, আছে ৳{bal:.2f}",reply_markup=main_kb(uid))
        resp=await api({"action":"add","service":r["provider_service_id"],"link":st["link"],"quantity":q})
        pid=str(resp.get("order","")) if isinstance(resp,dict) else ""
        if not pid:
            c.close(); states.pop(uid,None); return await update.message.reply_text(f"⚠️ Order হয়নি। Balance কাটা হয়নি।\nকারণ: {resp.get('error','Provider error')}",reply_markup=main_kb(uid))
        c.execute("BEGIN IMMEDIATE"); c.execute("UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?",(price,uid,price))
        cur=c.execute("INSERT INTO orders(user_id,service_id,service_name,link,qty,price,provider_order_id,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(uid,r["service_id"],r["name"],st["link"],q,price,pid,"processing",now()))
        oid=cur.lastrowid;c.commit();c.close();states.pop(uid,None)
        msg=f"✅ অর্ডার সফল হয়েছে!\n━━━━━━━━━━━━\n🆔 Order ID: #{oid}\n📦 সার্ভিস: {r['name']}\n📊 Qty: {q}\n💰 চার্জ: ৳{price:.2f}\n📌 Status: ⏳ Processing"
        await update.message.reply_text(msg,reply_markup=main_kb(uid))
        if ORDER_CHANNEL:
            try: await context.bot.send_message(ORDER_CHANNEL,f"🛒 নতুন অর্ডার #{oid}\n👤 @{update.effective_user.username or update.effective_user.first_name}\n📦 {r['name']}\n📊 Qty: {q}\n💰 ৳{price:.2f}\n📌 Processing")
            except Exception as e: log.warning(e)
    elif st["s"]=="method":
        if t not in ("📲 bKash","💎 TON"): return await update.message.reply_text("❌ নিচের button ব্যবহার করুন।")
        st.update(s="amount",method="bKash" if "bKash" in t else "TON"); await update.message.reply_text("💵 Amount লিখুন:")
    elif st["s"]=="amount":
        try:a=float(t)
        except:return await update.message.reply_text("❌ সঠিক amount লিখুন।")
        if a<=0:return await update.message.reply_text("❌ Amount 0-এর বেশি হতে হবে।")
        st.update(s="photo",amount=a)
        if st["method"]=="TON": msg=f"💎 {a:.2f} TON পাঠান:\n{TON_WALLET_ADDRESS}\n\n📸 তারপর screenshot পাঠান।"
        else: msg=f"📲 ৳{a:.2f} Send Money করুন:\n{BKASH_NUMBER}\n\n📸 তারপর screenshot পাঠান।"
        await update.message.reply_text(msg)
    elif st["s"]=="addsvc" and admin(uid):
        try:
            a=[x.strip() for x in t.split(",")]; assert len(a)==6
            c=conn();c.execute("INSERT INTO services(category,name,provider_service_id,rate,min_qty,max_qty) VALUES(?,?,?,?,?,?)",(a[0],a[1],a[2],float(a[3]),int(a[4]),int(a[5])));c.commit();c.close()
            states.pop(uid);await update.message.reply_text("✅ Service added.",reply_markup=admin_kb())
        except: await update.message.reply_text("❌ Format ভুল।")
    elif st["s"]=="broadcast" and admin(uid):
        c=conn(); ids=[x[0] for x in c.execute("SELECT user_id FROM users")];c.close(); ok=bad=0
        for x in ids:
            try:await context.bot.send_message(x,"📢 "+t);ok+=1
            except:bad+=1
            await asyncio.sleep(.03)
        states.pop(uid);await update.message.reply_text(f"✅ Sent: {ok}, Failed: {bad}",reply_markup=admin_kb())

async def photo_router(update,context):
    uid=update.effective_user.id; st=states.get(uid,{})
    if st.get("s")!="photo": return
    c=conn(); cur=c.execute("INSERT INTO deposits(user_id,amount,method,status,photo_id,created_at) VALUES(?,?,?,?,?,?)",(uid,st["amount"],st["method"],"pending",update.message.photo[-1].file_id,now()));did=cur.lastrowid;c.commit();c.close()
    kb=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Approve",callback_data=f"approve:{did}"),InlineKeyboardButton("❌ Reject",callback_data=f"reject:{did}")]])
    for aid in ADMIN_IDS:
        await context.bot.send_photo(aid,update.message.photo[-1].file_id,caption=f"💰 Deposit #{did}\n👤 User: {uid}\n💳 {st['method']}\n💵 Amount: {st['amount']:.2f}",reply_markup=kb)
    states.pop(uid);await update.message.reply_text("⏳ Deposit request admin-এর কাছে পাঠানো হয়েছে।",reply_markup=main_kb(uid))

async def callback(update,context):
    q=update.callback_query; await q.answer(); d=q.data; uid=q.from_user.id
    if d.startswith("status:"):
        oid=int(d.split(":")[1]);c=conn();r=c.execute("SELECT provider_order_id,status FROM orders WHERE order_id=? AND user_id=?",(oid,uid)).fetchone()
        if not r:c.close();return
        resp=await api({"action":"status","order":r["provider_order_id"]}); status=resp.get("status",r["status"]);c.execute("UPDATE orders SET status=? WHERE order_id=?",(status,oid));c.commit();c.close();await q.answer(f"📌 {status}",show_alert=True)
    elif d.startswith("del:") and admin(uid):
        c=conn();c.execute("DELETE FROM services WHERE service_id=?",(int(d.split(":")[1]),));c.commit();c.close();await q.edit_message_text("✅ Service deleted.")
    elif d.startswith(("approve:","reject:")) and admin(uid):
        action,did=d.split(":");did=int(did);c=conn();dep=c.execute("SELECT * FROM deposits WHERE deposit_id=?",(did,)).fetchone()
        if not dep or dep["status"]!="pending":c.close();return await q.answer("আগেই process করা হয়েছে।",show_alert=True)
        if action=="approve":
            c.execute("UPDATE deposits SET status='approved',approved_at=? WHERE deposit_id=? AND status='pending'",(now(),did))
            c.execute("UPDATE users SET balance=balance+? WHERE user_id=?",(dep["amount"],dep["user_id"]))
            ref=c.execute("SELECT referred_by FROM users WHERE user_id=?",(dep["user_id"],)).fetchone()["referred_by"]
            if ref:c.execute("UPDATE users SET balance=balance+? WHERE user_id=?",(REFERRAL_BONUS,ref))
            c.commit();c.close();await q.edit_message_caption(caption=f"✅ Deposit #{did} Approved")
            try:await context.bot.send_message(dep["user_id"],f"✅ Deposit approved!\n💰 ৳{dep['amount']:.2f} balance-এ যোগ হয়েছে।")
            except:pass
        else:
            c.execute("UPDATE deposits SET status='rejected' WHERE deposit_id=? AND status='pending'",(did,));c.commit();c.close();await q.edit_message_caption(caption=f"❌ Deposit #{did} Rejected")
            try:await context.bot.send_message(dep["user_id"],"❌ আপনার deposit request reject করা হয়েছে।")
            except:pass

def main():
    if not BOT_TOKEN: raise SystemExit("BOT_TOKEN missing in .env")
    init_db(); app=Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",start))
    app.add_handler(MessageHandler(filters.PHOTO,photo_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,text_router))
    app.add_handler(CallbackQueryHandler(callback))
    app.run_polling()

if __name__=="__main__": main()
