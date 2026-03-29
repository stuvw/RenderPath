#version 330 core
layout(location = 0) in vec2 position;
out vec2 vUv;
// Instead of: vUv = (position + 1.0) * 0.5;
// We now flip the frame here, removing one unnecessary call
void main() {
    vUv = vec2((position.x + 1.0) * 0.5, (1.0 - (position.y + 1.0) * 0.5)); 
    gl_Position = vec4(position, 0.0, 1.0);
}