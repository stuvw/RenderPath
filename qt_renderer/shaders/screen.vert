#version 330 core
layout(location = 0) in vec2 position;
uniform int flipY;   // 1 = flip for ffmpeg (top-down), 0 = normal preview
out vec2 vUv;
void main() {
    float u = (position.x + 1.0) * 0.5;
    float v = (position.y + 1.0) * 0.5;
    vUv = vec2(u, flipY == 1 ? 1.0 - v : v);
    gl_Position = vec4(position, 0.0, 1.0);
}