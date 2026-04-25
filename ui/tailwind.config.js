/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                background: '#0d0d0d',
                foreground: '#e0e0e0',
                accent: '#00f2ff',
                staging: '#1a1a1a',
            },
            fontFamily: {
                mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
                inter: ['Inter', 'system-ui', 'sans-serif'],
            },
        },
    },
    plugins: [],
}
