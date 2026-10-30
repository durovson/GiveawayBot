-- Granted once through creation of the user's unique Arena wallet.
-- Existing wallets and the protected reserve of 50 are unchanged.
alter table public.arena_wallets alter column balance set default 100;
