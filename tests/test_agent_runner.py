from app.agent.llm import ChatResult, FakeLLM, ToolCall
from app.agent.runner import run_agent
from app.agent.tools import ARG_MODELS


async def test_repair_loop_recovers_from_bad_args():
    # 1) el LLM manda args inválidos ($ = intento de inyección)
    # 2) tras ver el error, reintenta con args válidos
    # 3) responde en texto
    script = [
        ChatResult(tool_calls=[ToolCall("c1", "search_tracks_database", {"artist_name": "$evil"})]),
        ChatResult(tool_calls=[ToolCall("c2", "search_tracks_database", {"artist_name": "Bad Bunny"})]),
        ChatResult(content="Aquí tienes tu playlist 🎧"),
    ]
    llm = FakeLLM(script)
    executed = []

    async def search_exec(args):
        executed.append(args)
        return {"tracks": [{"uri": "spotify:track:1"}]}

    out = await run_agent(llm, {"search_tracks_database": search_exec}, ARG_MODELS, "haz una playlist")

    assert out == "Aquí tienes tu playlist 🎧"
    # el executor solo se llamó con los args VÁLIDOS (los malos se rechazaron antes)
    assert len(executed) == 1 and executed[0].artist_name == "Bad Bunny"
    # y el LLM recibió el mensaje de error de reparación
    assert any(
        m.get("role") == "tool" and "inválidos" in m.get("content", "")
        for msgs in llm.calls for m in msgs
    )


async def test_unknown_tool_is_reported():
    llm = FakeLLM([
        ChatResult(tool_calls=[ToolCall("c1", "no_existe", {})]),
        ChatResult(content="ok"),
    ])
    out = await run_agent(llm, {}, ARG_MODELS, "x")
    assert out == "ok"
