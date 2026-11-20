import {
  IBMPlexSans_400Regular,
  IBMPlexSans_500Medium,
  IBMPlexSans_600SemiBold,
  IBMPlexSans_700Bold,
  useFonts,
} from '@expo-google-fonts/ibm-plex-sans';
import { IBMPlexSansArabic_400Regular } from '@expo-google-fonts/ibm-plex-sans-arabic';
import { DarkTheme, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';

import { AuthProvider, useAuth } from '@/auth';
import AppTabs from '@/components/app-tabs';
import { AuthScreen } from '@/components/auth-screen';
import { OnboardingScreen } from '@/components/onboarding';
import { C } from '@/constants/theme';
import { DemoProvider } from '@/demo-data';
import '@/work-tracking'; // defines the background work-location task before Android needs it

SplashScreen.preventAutoHideAsync();

const theme = { ...DarkTheme, colors: { ...DarkTheme.colors, background: C.bg, card: C.bg, border: C.line } };

export default function TabLayout() {
  const [loaded, error] = useFonts({
    IBMPlexSans_400Regular,
    IBMPlexSans_500Medium,
    IBMPlexSans_600SemiBold,
    IBMPlexSans_700Bold,
    IBMPlexSansArabic_400Regular,
  });
  const ready = loaded || !!error; // if a font fails, still show the app (system font)

  useEffect(() => {
    if (ready) SplashScreen.hideAsync();
  }, [ready]);

  if (!ready) return null;
  return (
    <ThemeProvider value={theme}>
      <StatusBar style="light" />
      <AuthProvider>
        <Main />
      </AuthProvider>
    </ThemeProvider>
  );
}

function Main() {
  const { account, demoOnly, onboarding } = useAuth();
  if (!account && !demoOnly) return <AuthScreen />;
  if (account && onboarding) return <OnboardingScreen />;
  return (
    <DemoProvider key={account?.id ?? 'demo'}>
      <AppTabs />
    </DemoProvider>
  );
}
