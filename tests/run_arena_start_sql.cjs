// NODE_PATH=<test-runtime>/node_modules node tests/run_arena_start_sql.cjs
const {PGlite}=require('@electric-sql/pglite');
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
  const db=new PGlite();
  try {
    await db.exec(fs.readFileSync(path.join(__dirname,'sql/chat_games_bootstrap.sql'),'utf8'));
    await db.exec(fs.readFileSync(path.join(__dirname,'../supabase/migrations/20261028_arena_v2.sql'),'utf8'));
    await db.exec("insert into public.users(telegram_id) values(-93001),(-93002); select public.arena_balance(-93001);");
    const migration=fs.readFileSync(path.join(__dirname,'../supabase/migrations/20261030195714_arena_start_balance_100.sql'),'utf8');
    await db.exec(migration);
    await db.exec(`set role service_role;
      do $$ begin
        assert public.arena_balance(-93001)=50,'existing wallet preserved';
        assert public.arena_balance(-93002)=100,'new wallet starts with 100';
        assert public.arena_balance(-93002)=100,'repeated entry does not grant again';
        update public.arena_wallets set balance=70 where user_id=-93002;
        assert public.arena_balance(-93002)=70,'spent bonus does not replenish';
      end $$; reset role;`);
    await db.exec(migration);
    const result=await db.query('select balance from public.arena_wallets where user_id=-93002');
    if(Number(result.rows[0].balance)!==70) throw Error('migration replay changed balance');
    console.log('Arena starter: 100 once, existing wallets preserved, repeat migration safe.');
  } finally {await db.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
