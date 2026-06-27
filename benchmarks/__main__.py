"""Allow ``python -m benchmarks`` as a shortcut for ``python -m benchmarks.run``."""

from benchmarks.run import main
import asyncio

asyncio.run(main())
