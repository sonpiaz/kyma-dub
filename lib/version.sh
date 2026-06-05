#!/usr/bin/env bash
# Single source of truth for the kyma-dub version. Sourced by bin/kyma-dub
# (for --version) and by lib/env.sh (for the User-Agent header sent on Kyma
# calls so Kyma can attribute usage and detect stale installs).
#
# To cut a release: bump KYMA_DUB_VERSION below, open a release PR titled
# `release: vX.Y.Z`, merge, then tag the merge commit `vX.Y.Z` and push.

export KYMA_DUB_VERSION="0.2.0"
export KYMA_DUB_VERSION_STRING="kyma-dub v${KYMA_DUB_VERSION}"
