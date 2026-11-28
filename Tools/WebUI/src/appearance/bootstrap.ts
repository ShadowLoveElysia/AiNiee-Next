import { applyAnimationPreference, applyTheme, readPreferences } from './preferences';
import '../styles.css';

const preferences = readPreferences();
applyTheme(preferences.theme);
applyAnimationPreference(preferences.uiAnimations);
