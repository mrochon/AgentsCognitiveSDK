import asyncio
import os
from typing import Annotated

from semantic_kernel.agents.open_ai.azure_assistant_agent import AzureAssistantAgent
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.streaming_annotation_content import StreamingAnnotationContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from semantic_kernel.kernel import Kernel
from semantic_kernel.functions.kernel_function_decorator import kernel_function
from accessSql import SQL

def get_filepath_for_filename(filename: str) -> str:
    base_directory = os.path.dirname(os.path.realpath(__file__))
    return os.path.join(base_directory, filename)

from dotenv import load_dotenv
load_dotenv(override = True)
filenames = [
    "schema.json",
]

async def main() -> None:
    from azure.identity.aio import DefaultAzureCredential
    
    kernel = Kernel()
    sql = SQL()
    kernel.add_function("try_query", sql.execute)
    
    try:
        token = await DefaultAzureCredential().get_token("https://cognitiveservices.azure.com/.default")

        agent = await AzureAssistantAgent.create(
            kernel=kernel,
            ad_token=token.token,
            service_id="chat service",
            name="sqlGenerator",
            instructions="""
        You are an SQL expert who translates user requests into SQL queries. The database schema is provided to you. 
        Use only table and column names contained in that schema. Always use the value of the TABLE_SCHEMA column in the schema as prefix for the table name.
        You may only generate SELECT statements. Do not generate DLETE, INSERT or UPDATE statements.
        You must always include 'TOP 3' in the query.
        If you cannot generate a query, you can ask the user for more information or clarification. 
        If you can generate a query, call the try_query function with the query as an argument. 
        If the function responds with an error message, try correcting the original query or ask the user for more information. Otherwise, return the query to the user.
                """,
            enable_file_search=True,
            vector_store_filenames=[get_filepath_for_filename(filename) for filename in filenames],
        )

        print("Creating thread...")
        thread_id = await agent.create_thread()
        await sql.open()
        is_complete: bool = False
        while not is_complete:
            user_input = input("User:> ")
            if not user_input or user_input.isspace():
                is_complete = True
                break

            await agent.add_chat_message(
                thread_id=thread_id, message=ChatMessageContent(role=AuthorRole.USER, content=user_input)
            )

            footnotes: list[StreamingAnnotationContent] = []
            async for response in agent.invoke_stream(thread_id=thread_id):
                footnotes.extend([item for item in response.items if isinstance(item, StreamingAnnotationContent)])

                print(f"{response.content}", end="", flush=True)

            print()

            if len(footnotes) > 0:
                for footnote in footnotes:
                    print(
                        f"\n`{footnote.quote}` => {footnote.file_id} "
                        f"(Index: {footnote.start_index} - {footnote.end_index})"
                    )

    finally:
        print("Cleaning up resources...")
        if agent is not None:
            [await agent.delete_file(file_id) for file_id in agent.file_search_file_ids]
            await agent.delete_thread(thread_id)
            await agent.delete()
        await sql.close()


if __name__ == "__main__":
    asyncio.run(main())