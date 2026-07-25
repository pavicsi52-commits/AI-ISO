"""Real protocol scanners and cloud/Kubernetes enumeration providers.

See ``app/scanners/base.py`` (single-probe protocols) and
``app/scanners/enumeration.py`` (multi-resource cloud/Kubernetes
discovery) for the two complementary contracts every module in this
package implements, and ``app/scanners/registry.py`` for how
``app/services/discovery_execution.py`` looks either up.
"""

from __future__ import annotations
