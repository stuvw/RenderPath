#version 330 core
in vec3 vWorldPosition;
flat in vec2 vDataValue;
uniform vec3 cameraPosition;
out vec4 FragColor;

void main() {
    float d = distance(vWorldPosition, cameraPosition);
    // Removing glFrontFacing fixes an issue, and I don't know why it was here to begin with...
    // float s = gl_FrontFacing ? 1.0 : -1.0;
    // float f = s * d;
    FragColor = vec4(d * vDataValue.x, d * vDataValue.y, 0.0, 1.0);
}