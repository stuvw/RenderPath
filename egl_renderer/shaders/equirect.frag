/*
    Equirectangular Conversion Shader:  "unrolls" the cube faces into a 360 degree 2:1 projection.
*/

#version 330 core
in vec2 vUv;
uniform samplerCube cubemap;
uniform sampler2D colormap;
uniform float minVal;
uniform float maxVal;
uniform vec4 underColor;
uniform vec4 overColor;
uniform vec4 badColor;
out vec4 FragColor;

const float PI = 3.14159265359;
const float INV_LOG10 = 0.4342944819;

void main() {
    // flip vertical for ffmpeg (OpenGL is bottom-up, ffmpeg expects top-down)
    // vec2 uv = vec2(vUv.x, 1.0 - vUv.y); // Actually nvm

    // Map UV to spherical coordinates
    float phi = (vUv.x * 2.0 - 1.0) * PI;
    float theta = (vUv.y * 2.0 - 1.0) * (PI / 2.0);

    // Convert to direction vector (Y-up, phi negated to fix left-right mirror)
    vec3 dir = vec3(cos(theta) * sin(-phi), sin(theta), cos(theta) * cos(-phi));
    // Remap Y-up cubemap → Z-up world: swap Y and Z, negate the new Y
    dir = vec3(dir.x, dir.z, -dir.y);
    vec2 data = texture(cubemap, dir).rg;
    
    float w = data.g;
    if (w == 0.0) {
        FragColor = badColor;
        return;
    }

    float depth = log(data.r / w) * INV_LOG10;
    float t = (depth - minVal) / (maxVal - minVal);
    
    vec4 color = texture(colormap, vec2(clamp(t, 0.0, 1.0), 0.5));
    color = mix(underColor, color, step(0.0, t));
    color = mix(color, overColor, step(1.0, t));
    FragColor = color;
}