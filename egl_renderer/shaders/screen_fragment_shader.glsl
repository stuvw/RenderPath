#version 330 core
in vec2 vUv;

uniform sampler2D depthTexture;
uniform sampler2D colormap;
uniform float minVal;
uniform float maxVal;

uniform vec4 underColor;
uniform vec4 overColor;
uniform vec4 badColor;

out vec4 FragColor;

void main() {
    vec2 data = texture(depthTexture, vUv).rg;
    float qw = data.r;
    float w  = data.g;

    if (w == 0.0) {
        FragColor = badColor;
        return;
    }

    const float INV_LOG10 = 0.4342944819;
    float depth = log(qw / w) * INV_LOG10;

    // Branchless tone mapping
    float t = (depth - minVal) / (maxVal - minVal);
    vec4 color = texture(colormap, vec2(clamp(t, 0.0, 1.0), 0.5));
    color = mix(underColor, color, step(0.0, t));
    color = mix(color, overColor, step(1.0, t));
    FragColor = color;
}