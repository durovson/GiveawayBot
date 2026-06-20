import asyncio
import logging
import loader

holder_sync_lock = asyncio.Lock()
from typing import List, Dict, Optional
from database import db
from services.leaderboard import LeaderboardService
from services.points_service import PointsService
from utils import normalize_to_raw
import json

logger = logging.getLogger(__name__)

API_URL = "https://stickers.tools/api/v1/launching/packs/0:81abce045d81dc32c42aebc27b1ad6898bb4f89306231d2b58031908a4c267c7/holders"

async def fetch_holders():
    if holder_sync_lock.locked():
        logger.warning("Holder sync already running")
        return {"holders": [], "total": 0, "totalHeld": 0, "hasMore": False}

    async with holder_sync_lock:
        holders = []
        offset = 0
        limit = 30
        retries = 5

        total = 0
        total_held = 0
        has_more = False

        # Use shared session from loader
        session = loader.http_session
        if not session:
            logger.error("Shared HTTP session not initialized")
            return {"holders": [], "total": 0, "totalHeld": 0, "hasMore": False}

        while True:
            url = f"{API_URL}?offset={offset}&limit={limit}"
            payload = {}
            page = []

            for attempt in range(1, retries + 1):
                try:
                    async with session.get(url, timeout=30) as response:
                        if response.status != 200:
                            if attempt == retries:
                                return {"holders": holders, "total": 0, "totalHeld": 0, "hasMore": False}
                            await asyncio.sleep(attempt)
                            continue

                        response_json = await response.json()
                        payload = response_json.get("data", {}) if isinstance(response_json, dict) else {}
                        page = payload.get("holders", []) if isinstance(payload, dict) else []
                        has_more = payload.get("hasMore", False) if isinstance(payload, dict) else False
                        total = payload.get("total", 0) if isinstance(payload, dict) else 0
                        total_held = payload.get("totalHeld", 0) if isinstance(payload, dict) else 0

                        logger.info("HOLDERS_TOTAL=%s", total)
                        logger.info("HOLDERS_RECEIVED=%s", len(page))

                        break
                except (asyncio.TimeoutError, Exception) as e:
                    if attempt == retries:
                        logger.error("Holders API fetch failed after %s attempts: %s", retries, e)
                        return {"holders": holders, "total": 0, "totalHeld": 0, "hasMore": False}
                    await asyncio.sleep(attempt)

            valid = []
            for item in page:
                if not isinstance(item, dict):
                    continue
                addr = item.get("addr")
                if not addr:
                    continue
                try:
                    valid.append({
                        "wallet": normalize_to_raw(addr),
                        "packs": item.get("count", 0),
                        "rank": item.get("rank")
                    })
                except Exception:
                    continue
            holders.extend(valid)

            if not has_more:
                break
            if len(page) < limit:
                break
            offset += limit
            await asyncio.sleep(0.1)

        cached = {
            "holders": holders,
            "total": total,
            "totalHeld": total_held,
            "hasMore": has_more,
        }

        return cached

async def sync_points_and_referrals(holders: List[Dict]):
    """Syncs pack counts to the points table and awards referral income for new purchases."""
    try:
        linked_wallets = await db.get_all_linked_wallets()
        wallet_to_tg = {normalize_to_raw(w['wallet_address']): w['telegram_id'] for w in linked_wallets if w.get('wallet_address')}

        relevant_user_ids = [wallet_to_tg[h['wallet']] for h in holders if h['wallet'] in wallet_to_tg]
        if not relevant_user_ids:
            return

        # Batch fetch points and users
        all_pts = await db.get_points_batch(relevant_user_ids)
        pts_map = {p['user_id']: p for p in all_pts}

        # Batch fetch users for referrers lookup if needed
        all_users = await db.get_users_batch(relevant_user_ids)
        users_map = {u['telegram_id']: u for u in all_users}

        for h in holders:
            wallet = h['wallet']
            if wallet in wallet_to_tg:
                user_id = wallet_to_tg[wallet]
                current_packs = h['packs']

                pts = pts_map.get(user_id)
                if pts is None:
                    await db.upsert_points(user_id, packs=current_packs)
                    await PointsService.recalculate_points(user_id)
                else:
                    prev_packs = pts.get("packs", 0)
                    if current_packs != prev_packs:
                        await db.upsert_points(user_id, packs=current_packs)

                        if current_packs > prev_packs:
                            delta_packs = current_packs - prev_packs
                            
                            user = users_map.get(user_id)
                            
                            if user and user.get("referrer_id"):
                                referrer_id = user["referrer_id"]
                                ref_pts = await db.get_points(referrer_id)
                                
                                curr_income = (
                                    ref_pts.get("referral_income", 0)
                                    if ref_pts else 0
                                )
                                
                                referral_reward = delta_packs * 2
                                
                                await db.upsert_points(
                                    referrer_id,
                                    referral_income=curr_income + referral_reward
                                )
                            
                                await PointsService.recalculate_points(
                                    referrer_id
                                )
                        
                        await PointsService.recalculate_points(user_id)

    except Exception as e:
        logger.error(f"Error in sync_points_and_referrals: {e}")

async def daily_sync_task(bot):
    """Background task to sync holders from Stickers Tools API daily."""
    logger.info("Starting daily sync task")
    while True:
        try:
            cached = await fetch_holders()
            holders = cached.get("holders", []) if isinstance(cached, dict) else []

            if holders:
                try:
                    await db.save_snapshot(data=holders, snapshot_type="daily", total_held=cached.get("totalHeld", 0))
                    await db.cleanup_old_snapshots(days=14)
                except Exception:
                    logger.exception("Snapshot save failed")

                # Sync points for linked wallets
                await sync_points_and_referrals(holders)

                LeaderboardService.invalidate_cache()
                logger.info("Holders snapshot and points updated")
            else:
                logger.warning("Holders API returned empty dataset. Skipping update.")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error in daily_sync_task: {e}", exc_info=True)

        # Sleep for 8 hours
        await asyncio.sleep(8 * 3600)

MILESTONES = (333, 666, 1000)

async def milestone_monitor_task(bot):
    """Background task to monitor collection growth milestones every 60 seconds."""
    logger.info("Starting milestone monitor task")
    while True:
        try:
            # 1. Fetch current data
            cached = await fetch_holders()
            holders = cached.get("holders", [])
            current_total = cached.get("totalHeld", 0)

            if not holders:
                logger.warning("Milestone monitor: API returned empty dataset")
                await asyncio.sleep(60)
                continue

            # 2. Get baseline
            previous_total = await db.get_last_total_held()

            if previous_total is None:
                # First run after migration: initialize baseline and skip milestone detection
                logger.info("Initializing milestone baseline: %s", current_total)
                await db.save_snapshot(
                    data=holders,
                    snapshot_type="daily",
                    total_held=current_total
                )
            else:
                # Sync points for linked wallets frequently
                await sync_points_and_referrals(holders)

                # 3. Detect milestone crossings
                for target in MILESTONES:
                    if previous_total < target <= current_total:
                        # Double check if milestone already exists in DB to prevent duplicates on restart
                        if not await db.milestone_exists(target):
                            logger.info("Milestone %s reached! (Total: %s)", target, current_total)
                            await db.save_snapshot(
                                data=holders,
                                snapshot_type="milestone",
                                total_held=current_total,
                                milestone=target
                            )
                        else:
                            logger.info("Milestone %s already exists in database, skipping", target)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error in milestone_monitor_task: {e}", exc_info=True)

        await asyncio.sleep(60)
