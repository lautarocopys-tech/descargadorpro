#!/usr/bin/env bash
# Script para descargar FFmpeg estático en Render
set -e

echo "--- Installing FFmpeg ---"
# Crear carpeta para binarios si no existe
mkdir -p bin
cd bin

# Descargar build estático de FFmpeg
if [ ! -f "ffmpeg" ]; then
    wget -q https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
    tar xf ffmpeg-release-amd64-static.tar.xz --strip-components=1
    rm ffmpeg-release-amd64-static.tar.xz
    echo "FFmpeg installed successfully."
else
    echo "FFmpeg already exists, skipping download."
fi

cd ..
echo "--- Build complete ---"
