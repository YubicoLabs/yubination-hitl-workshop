# monitor.py
import asyncio
import nats
import os


async def main():
    nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
    nc = await nats.connect(nats_url)
    js = nc.jetstream()

    stream_name = "tasks"

    print(f"Monitoring stream '{stream_name}'. Press Ctrl+C to exit.")

    while True:
        try:
            stream_info = await js.stream_info(stream_name)
            total_in_stream = stream_info.state.messages

            total_pending_for_consumers = 0
            total_in_progress = 0
            consumer_details = []

            consumers_info = await js.consumers_info(stream_name)
            for consumer_info in consumers_info:
                total_pending_for_consumers += consumer_info.num_pending
                in_progress = consumer_info.num_ack_pending
                total_in_progress += in_progress
                consumer_details.append(
                    f"{consumer_info.name}: {in_progress} in-progress, {consumer_info.num_pending} pending"
                )

            details_str = " | ".join(consumer_details)
            print(
                f"\rQueue Status | Pending: {total_pending_for_consumers} | In-Progress: {total_in_progress} | Total in Stream: {total_in_stream} ({details_str})  ",
                end="",
            )

            await asyncio.sleep(1)

        except nats.errors.Error:
            print(f"Stream '{stream_name}' not found. Waiting...")
            await asyncio.sleep(2)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\nAn error occurred: {e}")
            break

    print("\nMonitor stopped.")
    await nc.close()


if __name__ == "__main__":
    asyncio.run(main())
