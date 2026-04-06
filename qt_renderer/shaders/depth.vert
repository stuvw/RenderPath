#version 330 core
layout(location = 0) in vec3 position;
layout(location = 1) in vec4 posScale;
layout(location = 5) in float quantity;
layout(location = 6) in float weight;

uniform mat4 projection;
uniform mat4 view;
uniform float globalScale;

out vec3 vWorldPosition;
flat out vec2 vDataValue;

void main() {
    vec3 scaledPos = position * globalScale * posScale.w;
    vec3 worldPos  = scaledPos + posScale.xyz;
    vWorldPosition = worldPos;
    vDataValue     = vec2(quantity * weight, weight) / (posScale.w * posScale.w);
    gl_Position    = projection * view * vec4(worldPos, 1.0);
}