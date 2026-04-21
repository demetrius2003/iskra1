"""Output channels."""

from iskra.core.config import OutputConfig
from iskra.output.console_output import ConsoleOutput
from iskra.output.file_output import FileOutput
from iskra.output.protocol import OutputChannel


def create_output_channel(config: OutputConfig) -> OutputChannel:
    ch = config.channel
    settings = dict(config.settings.get(ch, {}))
    if ch == "console":
        return ConsoleOutput(settings)
    if ch == "file":
        return FileOutput(settings)
    raise ValueError(f"Unknown output channel: {ch}")
