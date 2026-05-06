from models.documents.queued_message import QueuedMessage


async def queue_message(link_token: str, msg_type: str, payload: dict) -> None:
    msg = QueuedMessage(link_token=link_token, msg_type=msg_type, payload=payload)
    await msg.insert()


async def fetch_and_delete_queued_messages(link_token: str) -> list[dict]:
    messages = await QueuedMessage.find(
        QueuedMessage.link_token == link_token
    ).to_list()

    result = [{"msg_type": msg.msg_type, "payload": msg.payload} for msg in messages]

    for msg in messages:
        await msg.delete()

    return result
