"""
Build script: compile target Python files to Cython C extensions.
Run from the StudioKit root directory:
    python build_cython.py build_ext --inplace
"""
from setuptools import setup, Extension
from Cython.Build import cythonize
import sys
import os

# Files to compile. Paths are relative to the StudioKit root.
TARGETS = [
    "hypecutter/core_engine.py",
    "license_guard.py",
    "license_client.py",
    "scene_manager/analyzer.py",
    "scene_manager/classifier.py",
]

extensions = []
for target in TARGETS:
    # Module name: hypecutter/core_engine.py -> hypecutter.core_engine
    module_name = target.replace("/", ".").replace("\\", ".").replace(".py", "")
    ext = Extension(
        name=module_name,
        sources=[target],
        extra_compile_args=["/O2"] if sys.platform == "win32" else ["-O2"],
    )
    extensions.append(ext)

setup(
    name="studiokit_extensions",
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            "language_level": "3",
            "boundscheck": False,
            "wraparound": False,
        },
        quiet=True,
    ),
)
