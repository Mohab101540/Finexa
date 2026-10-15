import Ionicons from '@expo/vector-icons/Ionicons';
import { Tabs } from 'expo-router';
import { ComponentProps } from 'react';

import { C, F } from '@/constants/theme';

type IconName = ComponentProps<typeof Ionicons>['name'];

const TABS: { name: string; title: string; icon: IconName }[] = [
  { name: 'index', title: 'Home', icon: 'home' },
  { name: 'inbox', title: 'Inbox', icon: 'chatbox-ellipses' },
  { name: 'try-sms', title: 'Try SMS', icon: 'flask' },
  { name: 'history', title: 'History', icon: 'receipt' },
  { name: 'outlook', title: 'Outlook', icon: 'pie-chart' },
];

export default function AppTabs() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        sceneStyle: { backgroundColor: C.bg },
        tabBarStyle: { backgroundColor: C.bg, borderTopColor: C.line },
        tabBarActiveTintColor: C.text,
        tabBarInactiveTintColor: C.faint,
        tabBarLabelStyle: { fontFamily: F.semibold, fontSize: 11 },
      }}>
      {TABS.map((t) => (
        <Tabs.Screen
          key={t.name}
          name={t.name}
          options={{
            title: t.title,
            tabBarIcon: ({ focused, size }) => (
              <Ionicons name={t.icon} size={size} color={focused ? C.indigo : C.faint} />
            ),
          }}
        />
      ))}
    </Tabs>
  );
}
