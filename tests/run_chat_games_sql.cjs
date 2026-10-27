// npm install --prefix <temporary-folder> @electric-sql/pglite@0.5.12
// NODE_PATH=<temporary-folder>/node_modules node tests/run_chat_games_sql.cjs
const { PGlite } = require('@electric-sql/pglite');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const db = new PGlite();
  try {
    await db.exec(fs.readFileSync(path.join(__dirname,'sql/chat_games_bootstrap.sql'),'utf8'));
    await db.exec(fs.readFileSync(path.join(__dirname,'../supabase/migrations/20261027124829_chat_bank_robber.sql'),'utf8'));
    await db.exec(`create table public.chats(chat_id bigint primary key,title text,chat_type text,created_at timestamptz default now());
      create function public.set_updated_at() returns trigger language plpgsql as $$begin new.updated_at=now(); return new; end$$;
      create trigger trg_chats_updated_at before update on public.chats for each row execute function public.set_updated_at();`);
    await db.exec(fs.readFileSync(path.join(__dirname,'../supabase/migrations/20261027185608_fix_chat_tracking_profile.sql'),'utf8'));
    await db.exec(fs.readFileSync(path.join(__dirname,'sql/chat_games_rollback.sql'),'utf8'));
    await db.exec(fs.readFileSync(path.join(__dirname,'sql/chat_profile_rollback.sql'),'utf8'));
    console.log('Bank Robber SQL integration: all assertions passed; fixtures rolled back.');
  } finally { await db.close(); }
})().catch(error => { console.error(error); process.exitCode=1; });
