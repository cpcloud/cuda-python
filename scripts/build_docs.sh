#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -eo pipefail

SRC_DIR="$1"

pushd "$SRC_DIR/docs" || exit 1

export SPHINX_PKG_VER
SPHINX_PKG_VER="$(python -m setuptools_scm)"

export SPHINXOPTS
SPHINXOPTS="-j $(nproc) -d $PWD/build/.doctrees"

make html

# to support version dropdown menu
if test -e ./versions.json; then
  cp ./versions.json build/html
fi
cp ./nv-versions.json build/html

# to have a redirection page (to the latest docs)
cp source/_templates/main.html build/html/index.html

mv "build/html/${SPHINX_PKG_VER}" build/html/latest

# ensure that the Sphinx reference uses the latest docs
cp build/html/latest/objects.inv build/html

# clean up previously auto-generated files
rm -rf source/generated/

popd || exit 1
