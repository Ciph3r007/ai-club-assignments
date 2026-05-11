"""Session context re-export.

``SessionContext`` lives in ``querygraph_agent.api.service`` (the stable public
API module).  This module re-exports it so that code in the ``session``
sub-package can import from a single canonical location without duplicating
the definition.

REQ-CTX-001: Every agent turn must carry both ``thread_id`` and ``user_id``.
"""

from querygraph_agent.api.service import SessionContext

__all__ = ["SessionContext"]
