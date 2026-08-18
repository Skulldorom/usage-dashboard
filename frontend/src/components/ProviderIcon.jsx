import HttpRoundedIcon from '@mui/icons-material/HttpRounded'

// Renders a provider brand mark from icon data served by the dashboard
// /providers API (viewBox + path), falling back to a generic glyph for
// providers without a mark (custom endpoints) or before the provider list
// has loaded. Marks render as fill="currentColor" to match the theme.
export default function ProviderIcon({ icon }) {
  if (icon?.viewBox && icon.path) {
    return <svg viewBox={icon.viewBox} width="1em" height="1em" fill="currentColor"><path d={icon.path} /></svg>
  }
  return <HttpRoundedIcon fontSize="inherit" />
}
