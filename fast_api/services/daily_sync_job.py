import asyncio
import datetime
from services.sync_services_data import fetch_and_sync_services
import core.config as cfg

async def run_daily_at_3am():
    while True:
        now = datetime.datetime.now()
        
        target = now.replace(hour=3, minute=0, second=0, microsecond=0)
        
        if now >= target:
            target += datetime.timedelta(days=1)
            
        sleep_seconds = (target - now).total_seconds()
        print(f"Next sync is scheduled at {target.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Sleeping for {sleep_seconds:.0f} seconds...")
        
        await asyncio.sleep(sleep_seconds)
        
        print("Time reached! Starting scheduled sync...")
        try:
            await fetch_and_sync_services(cfg.AsyncSessionLocal)
        except Exception as e:
            print(f"Error during scheduled sync: {e}")

if __name__ == "__main__":
    asyncio.run(run_daily_at_3am())
