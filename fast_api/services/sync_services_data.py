import random
import services.etermin_api.request_handler as rh
from  core import constants as c, config as cfg
from models.db_models import Service
import asyncio


async def fetch_and_sync_services(session_factory):
    async with session_factory() as session:
        try:
            print("sync executed!")
            for office, (webid, _) in c.OFFICE_COLLECTION.items():
                jitter = random.uniform(15.0, 30.0)
                print(f"waiting for {jitter: .2f} seconds before requesting {office}")
                await asyncio.sleep(jitter)
                groups = await rh.get_services(webid, office)
                if not groups:
                    print(f"Skipping empty or failed office: {office}")
                    continue
                for _, group_value in groups.items():
                    for _, service_value in group_value.items():
                        try:
                            async with session.begin_nested():
                                service_obj = Service(**service_value)
                                await session.merge(service_obj)
                        except Exception as inner_error:
                            print(f"Failed to merge a service in {office}: {inner_error}")
                            continue

            await session.commit()
            print("All services synced and committed successfully!")
        except Exception as e:
            await session.rollback()
            print(f"Fatal error occured, transaction rolled back: {e}")

if __name__ == "__main__":
    asyncio.run(fetch_and_sync_services(cfg.AsyncSessionLocal))
