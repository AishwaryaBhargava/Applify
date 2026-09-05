/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      // The sidebar becomes a slide-over below this width.
      screens: {
        // The narrowest phones (320px) get one step of their own, below
        // Tailwind's `sm`, for the few places two columns simply do not fit.
        xs: '360px',
        // The sidebar becomes a slide-over below this width.
        nav: '900px',
      },
      colors: {
        teal: {
          deep: '#0F6E56',
          medium: '#1D9E75',
          light: '#E1F5EE',
          soft: '#9FE1CB',
          ink: '#085041',
        },
        coral: {
          DEFAULT: '#D85A30',
          light: '#FAECE7',
          ink: '#712B13',
        },
        amber: {
          DEFAULT: '#EF9F27',
          light: '#FAEEDA',
          ink: '#412402',
        },
        bg: '#FAF9F7',
        card: '#FFFFFF',
        surface: {
          DEFAULT: '#F8F7F4',
          warm: '#F1EFE8',
        },
        border: {
          DEFAULT: '#E8E6E0',
          input: '#D3D1C7',
        },
        text: {
          primary: '#2C2C2A',
          secondary: '#5F5E5A',
          muted: '#888780',
          faint: '#B4B2A9',
        },
      },
      fontFamily: {
        serif: ['Georgia', 'Cambria', '"Times New Roman"', 'serif'],
        sans: [
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'Roboto',
          '"Helvetica Neue"',
          'Arial',
          'sans-serif',
        ],
      },
      fontSize: {
        hero: ['38px', { lineHeight: '1.2' }],
      },
      borderRadius: {
        badge: '4px',
        pill: '6px',
        input: '8px',
        btn: '10px',
        box: '12px',
        card: '14px',
        panel: '16px',
      },
      borderWidth: {
        hairline: '0.5px',
      },
      maxWidth: {
        hero: '600px',
      },
    },
  },
  plugins: [],
}
