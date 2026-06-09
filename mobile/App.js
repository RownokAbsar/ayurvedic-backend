import React, { useState, useEffect } from 'react';
import {
  StyleSheet, Text, View, TextInput, TouchableOpacity,
  ScrollView, ActivityIndicator, Image, Linking, Alert, Platform
} from 'react-native';
import * as Location from 'expo-location';
import { Audio } from 'expo-av';
import { Ionicons } from '@expo/vector-icons';
import * as Speech from 'expo-speech';

// ── Change this to your laptop's local IP ──────────────────────────────────
const API_URL = 'ayurvedic-backend-production.up.railway.app';
// ───────────────────────────────────────────────────────────────────────────

export default function App() {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState([]);
  const [message, setMessage] = useState('');
  const [directionsLoading, setDirectionsLoading] = useState({});
  const [recording, setRecording] = useState();
  const [isRecording, setIsRecording] = useState(false);

  const searchSymptoms = async () => {
    if (!query.trim()) return;
    Speech.stop();
    setLoading(true);
    setResults([]);
    setMessage('');

    try {
      const response = await fetch(`${API_URL}/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
      });
      if (!response.ok) {
        const text = await response.text();
        console.error('API error', response.status, text);
        throw new Error(`Server responded with ${response.status}`);
      }
      const data = await response.json();
      setResults(data.plants || []);
      setMessage(data.message);
    } catch (error) {
      console.error(error);
      setMessage('Network error. Ensure FastAPI is running and both devices are on the same Wi-Fi.');
    } finally {
      setLoading(false);
    }
  };

  // ── Voice Search ────────────────────────────────────────────────────────
  async function startRecording() {
    try {
      const permission = await Audio.requestPermissionsAsync();
      if (permission.status === 'granted') {
        await Audio.setAudioModeAsync({
          allowsRecordingIOS: true,
          playsInSilentModeIOS: true,
        });

        setIsRecording(true);
        setMessage(''); // Clear previous messages

        const { recording } = await Audio.Recording.createAsync(
          Audio.RecordingOptionsPresets.HIGH_QUALITY
        );
        setRecording(recording);
      } else {
        Alert.alert('Permission Denied', 'Please grant microphone permissions to use voice search.');
      }
    } catch (err) {
      console.error('Failed to start recording', err);
      setIsRecording(false);
      Alert.alert('Error', 'Failed to start recording.');
    }
  }

  async function stopRecording() {
    setIsRecording(false);
    if (!recording) return;

    try {
      await recording.stopAndUnloadAsync();
      const uri = recording.getURI();
      setRecording(undefined);

      // Complete reset of audio mode
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: false,
        playsInSilentModeIOS: true,
        playThroughEarpieceAndroid: false,
        staysActiveInBackground: false,
        interruptionModeIOS: 1,
        interruptionModeAndroid: 1,
        shouldDuckAndroid: true,
      });

      sendVoiceSearch(uri);
    } catch (err) {
      console.error('Failed to stop recording', err);
    }
  }

  const sendVoiceSearch = async (uri) => {
    Speech.stop();
    setLoading(true);
    setResults([]);
    setMessage('Processing voice audio...');

    try {
      // Get filename from uri
      const filename = uri.split('/').pop();
      const match = /\.(\w+)$/.exec(filename);
      const type = match ? `audio/${match[1]}` : `audio`;

      const formData = new FormData();
      formData.append('file', {
        uri,
        name: filename,
        type,
      });

      const response = await fetch(`${API_URL}/voice`, {
        method: 'POST',
        body: formData,
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      if (!response.ok) {
        const text = await response.text();
        console.error('API error', response.status, text);
        throw new Error(`Server responded with ${response.status}`);
      }

      const data = await response.json();

      // Update text input with the recognized query
      if (data.original_query) {
        setQuery(data.original_query);
      }

      setResults(data.plants || []);
      setMessage(data.message);

      // Speak the results
      if (data.plants && data.plants.length > 0) {
        // Force audio routing to speaker right before speaking again
        try {
          await Audio.setAudioModeAsync({
            allowsRecordingIOS: false,
            playsInSilentModeIOS: true,
            playThroughEarpieceAndroid: false,
            staysActiveInBackground: false,
            interruptionModeIOS: 1,
            interruptionModeAndroid: 1,
            shouldDuckAndroid: true,
          });
        } catch (e) { console.warn(e); }

        // Delay to let hardware switch routes completely
        await new Promise(resolve => setTimeout(resolve, 800));

        const topPlant = data.plants[0];
        const plantName = topPlant.parsed_main_name || topPlant.plant_name;
        let explanation = topPlant.clinical_explanation || topPlant.medicinal_uses || '';
        explanation = explanation.replace(/\*/g, ''); // Remove markdown bold/italic asterisks
        // Read only the first two sentences for brevity
        const shortExplanation = explanation.split(/(?<=[.!?])\s+/).slice(0, 2).join(' ');

        let speechText = `I found ${plantName}. ${shortExplanation}`;

        // Add dosage information if available
        if (topPlant.formatted_dosage && topPlant.formatted_dosage.dose) {
          // Replace | with a space for natural speech
          const cleanDose = topPlant.formatted_dosage.dose.replace(/\s*\|\s*/g, ' ');
          speechText += ` The recommended dosage is ${cleanDose}.`;

          if (topPlant.formatted_dosage.part_used) {
            speechText += ` Using the ${topPlant.formatted_dosage.part_used}.`;
          }
        }

        Speech.speak(speechText, { rate: 0.95, volume: 1.0 });
      } else if (data.message) {
        Speech.speak(data.message.replace(/\*/g, ''), { rate: 0.95, volume: 1.0 });
      }

    } catch (error) {
      console.error(error);
      setMessage('Network error. Ensure FastAPI is running and both devices are on the same Wi-Fi.');
    } finally {
      setLoading(false);
    }
  };

  // ── Get Directions ────────────────────────────────────────────────────────
  const openDirections = async (loc, key) => {
    setDirectionsLoading(prev => ({ ...prev, [key]: true }));
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert(
          'Location Permission Required',
          'Please allow location access to get directions.'
        );
        return;
      }

      const userPos = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      });
      const { latitude: userLat, longitude: userLng } = userPos.coords;
      const { latitude: destLat, longitude: destLng } = loc;

      // Build platform-specific maps URL with directions
      let mapsUrl;
      if (Platform.OS === 'ios') {
        // Apple Maps with directions
        mapsUrl = `maps://app?saddr=${userLat},${userLng}&daddr=${destLat},${destLng}`;
        const canOpen = await Linking.canOpenURL(mapsUrl);
        if (!canOpen) {
          // Fallback to Google Maps URL
          mapsUrl = `https://www.google.com/maps/dir/?api=1&origin=${userLat},${userLng}&destination=${destLat},${destLng}&travelmode=walking`;
        }
      } else {
        // Google Maps on Android (intent URI)
        mapsUrl = `google.navigation:q=${destLat},${destLng}&mode=w`;
        const canOpen = await Linking.canOpenURL(mapsUrl);
        if (!canOpen) {
          mapsUrl = `https://www.google.com/maps/dir/?api=1&origin=${userLat},${userLng}&destination=${destLat},${destLng}&travelmode=walking`;
        }
      }

      await Linking.openURL(mapsUrl);
    } catch (err) {
      console.error('Directions error:', err);
      Alert.alert('Error', 'Could not open maps. Please try again.');
    } finally {
      setDirectionsLoading(prev => ({ ...prev, [key]: false }));
    }
  };
  // ─────────────────────────────────────────────────────────────────────────

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>🌿 Ayurvedic AI</Text>
        <Text style={styles.headerSubtitle}>Discover natural remedies</Text>
      </View>

      <View style={styles.searchContainer}>
        <TextInput
          style={styles.input}
          placeholder="Symptoms (e.g. fever, joint pain)"
          placeholderTextColor="#aaa"
          value={query}
          onChangeText={setQuery}
          onSubmitEditing={searchSymptoms}
          returnKeyType="search"
        />
        <TouchableOpacity
          style={[styles.voiceButton, isRecording && styles.voiceButtonRecording]}
          onPress={isRecording ? stopRecording : startRecording}
        >
          <Ionicons name={isRecording ? "stop" : "mic"} size={24} color="#fff" />
        </TouchableOpacity>
        <TouchableOpacity style={styles.button} onPress={searchSymptoms}>
          <Text style={styles.buttonText}>Search</Text>
        </TouchableOpacity>
      </View>

      {loading && (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color="#2e7d32" />
          <Text style={styles.loadingText}>Analyzing database...</Text>
        </View>
      )}

      {message !== '' && !loading && results.length === 0 && (
        <Text style={styles.messageText}>{message}</Text>
      )}

      <ScrollView style={styles.resultsContainer} contentContainerStyle={{ paddingBottom: 40 }}>
        {results.map((plant, index) => (
          <View key={index} style={styles.card}>
            {/* ── Card Header ── */}
            <View style={styles.cardHeader}>
              <Text style={styles.plantName}>{plant.parsed_main_name || plant.plant_name}</Text>
              {plant.has_nearby_specimen && (
                <View style={styles.badge}>
                  <Text style={styles.badgeText}>📍 Nearby</Text>
                </View>
              )}
            </View>

            {/* ── Plant Image with fallback ── */}
            {plant.images && plant.images.length > 0 && (
              <PlantImage uri={plant.images[0]} />
            )}

            {/* ── Details Grid ── */}
            <View style={styles.detailsGrid}>
              <View style={styles.detailCol}>
                {plant.parsed_common_name && <Text style={styles.detailText}><Text style={styles.detailLabel}>Common: </Text>{plant.parsed_common_name}</Text>}
                {plant.parsed_family && <Text style={styles.detailText}><Text style={styles.detailLabel}>Family: </Text>{plant.parsed_family}</Text>}
                {plant.parsed_habit && <Text style={styles.detailText}><Text style={styles.detailLabel}>Habit: </Text>{plant.parsed_habit}</Text>}
                {plant.parsed_parts_used && <Text style={styles.detailText}><Text style={styles.detailLabel}>Parts: </Text>{plant.parsed_parts_used}</Text>}
              </View>
              <View style={styles.detailCol}>
                {plant.parsed_vernacular_name && <Text style={styles.detailText}><Text style={styles.detailLabel}>Local: </Text>{plant.parsed_vernacular_name}</Text>}
                {plant.parsed_habitat && <Text style={styles.detailText}><Text style={styles.detailLabel}>Habitat: </Text>{plant.parsed_habitat}</Text>}
                {plant.parsed_distribution && <Text style={styles.detailText}><Text style={styles.detailLabel}>Dist: </Text>{plant.parsed_distribution}</Text>}
              </View>
            </View>

            {/* ── Medicinal Uses ── */}
            <Text style={styles.usesTitle}>Medicinal Uses:</Text>
            <Text style={styles.usesText}>{plant.medicinal_uses}</Text>

            {/* ── Dosage ── */}
            {plant.formatted_dosage && (
              <View style={styles.dosageContainer}>
                <Text style={styles.dosageTitle}>📏 Verified Dosage</Text>
                {plant.formatted_dosage.dose && (
                  <Text style={styles.dosageText}><Text style={{ fontWeight: 'bold' }}>Dose: </Text>{plant.formatted_dosage.dose}</Text>
                )}
                {plant.formatted_dosage.part_used && (
                  <Text style={styles.dosageText}><Text style={{ fontWeight: 'bold' }}>Part: </Text>{plant.formatted_dosage.part_used}</Text>
                )}
              </View>
            )}

            {/* ── Clinical Guidance ── */}
            {plant.clinical_explanation && (
              <View style={styles.clinicalContainer}>
                <Text style={styles.clinicalTitle}>🤖 Clinical Guidance</Text>
                <Text style={styles.clinicalText}>{plant.clinical_explanation}</Text>
              </View>
            )}

            {/* ── Nearby Locations with Get Directions button ── */}
            {plant.nearby_locations && plant.nearby_locations.length > 0 && (
              <View style={styles.nearbyContainer}>
                <Text style={styles.nearbyTitle}>📍 Live Specimen Locations</Text>
                {plant.nearby_locations.map((loc, i) => {
                  const key = `${index}-${i}`;
                  const isLoadingDir = directionsLoading[key];
                  return (
                    <View key={i} style={styles.locCard}>
                      {loc.specimen_photo_url && (
                        <Image
                          source={{ uri: loc.specimen_photo_url }}
                          style={styles.nearbyImage}
                          resizeMode="cover"
                        />
                      )}
                      <Text style={styles.locDesc}>{loc.location_description}</Text>
                      {loc.notes && <Text style={styles.locNotes}>"{loc.notes}"</Text>}
                      <Text style={styles.locCoords}>🗺 {loc.latitude?.toFixed(5)}, {loc.longitude?.toFixed(5)}</Text>

                      {/* ── Get Directions Button ── */}
                      <TouchableOpacity
                        style={[styles.directionsBtn, isLoadingDir && styles.directionsBtnDisabled]}
                        onPress={() => openDirections(loc, key)}
                        disabled={isLoadingDir}
                        activeOpacity={0.8}
                      >
                        {isLoadingDir ? (
                          <ActivityIndicator size="small" color="#fff" />
                        ) : (
                          <Text style={styles.directionsBtnText}>🧭 Get Directions</Text>
                        )}
                      </TouchableOpacity>
                    </View>
                  );
                })}
              </View>
            )}
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

// ── Separate component to handle image errors gracefully ──────────────────
function PlantImage({ uri }) {
  const [error, setError] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    setError(false);
    setLoaded(false);
  }, [uri]);

  if (error) {
    return (
      <View style={styles.imageFallback}>
        <Text style={styles.imageFallbackText}>🌿 Image unavailable</Text>
      </View>
    );
  }

  return (
    <View>
      {!loaded && (
        <View style={styles.imageLoading}>
          <ActivityIndicator size="small" color="#4caf50" />
        </View>
      )}
      <Image
        source={{ uri }}
        style={[styles.plantImage, !loaded && { position: 'absolute', opacity: 0 }]}
        resizeMode="cover"
        onLoad={() => setLoaded(true)}
        onError={() => setError(true)}
      />
    </View>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f7f5', paddingTop: 60 },
  header: { paddingHorizontal: 20, marginBottom: 20 },
  headerTitle: { fontSize: 28, fontWeight: 'bold', color: '#1b5e20' },
  headerSubtitle: { fontSize: 16, color: '#4caf50', marginTop: 4 },

  searchContainer: { flexDirection: 'row', paddingHorizontal: 20, marginBottom: 20 },
  input: {
    flex: 1, backgroundColor: '#fff', borderWidth: 1, borderColor: '#c8e6c9',
    borderRadius: 12, paddingHorizontal: 15, paddingVertical: 12, fontSize: 16,
    marginRight: 10, color: '#333',
    shadowColor: '#000', shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05, shadowRadius: 4, elevation: 2,
  },
  button: {
    backgroundColor: '#2e7d32', justifyContent: 'center', alignItems: 'center',
    borderRadius: 12, paddingHorizontal: 20,
    shadowColor: '#2e7d32', shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3, shadowRadius: 6, elevation: 4,
  },
  voiceButton: {
    backgroundColor: '#4caf50', justifyContent: 'center', alignItems: 'center',
    borderRadius: 12, paddingHorizontal: 15, marginRight: 10,
    shadowColor: '#4caf50', shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3, shadowRadius: 6, elevation: 4,
  },
  voiceButtonRecording: {
    backgroundColor: '#d32f2f',
    shadowColor: '#d32f2f',
  },
  buttonText: { color: '#fff', fontWeight: 'bold', fontSize: 16 },

  loadingContainer: { alignItems: 'center', marginTop: 40 },
  loadingText: { marginTop: 12, color: '#2e7d32', fontSize: 16 },
  messageText: { textAlign: 'center', color: '#d32f2f', marginHorizontal: 20, marginTop: 20, fontSize: 16 },

  resultsContainer: { flex: 1, paddingHorizontal: 20 },
  card: {
    backgroundColor: '#fff', borderRadius: 16, padding: 20, marginBottom: 16,
    borderLeftWidth: 6, borderLeftColor: '#4caf50',
    shadowColor: '#000', shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.08, shadowRadius: 8, elevation: 4,
  },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  plantName: { fontSize: 20, fontWeight: '800', color: '#1b5e20', flex: 1 },
  badge: { backgroundColor: '#e8f5e9', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12, borderWidth: 1, borderColor: '#c8e6c9' },
  badgeText: { color: '#2e7d32', fontSize: 12, fontWeight: 'bold' },

  plantImage: { width: '100%', height: 200, borderRadius: 12, marginBottom: 12 },
  imageLoading: {
    width: '100%', height: 200, borderRadius: 12, marginBottom: 12,
    backgroundColor: '#e8f5e9', justifyContent: 'center', alignItems: 'center',
  },
  imageFallback: {
    width: '100%', height: 80, borderRadius: 12, marginBottom: 12,
    backgroundColor: '#f1f8e9', justifyContent: 'center', alignItems: 'center',
    borderWidth: 1, borderColor: '#c8e6c9', borderStyle: 'dashed',
  },
  imageFallbackText: { color: '#81c784', fontSize: 14 },

  detailsGrid: {
    flexDirection: 'row', justifyContent: 'space-between',
    backgroundColor: '#f9fbe7', padding: 12, borderRadius: 10, marginBottom: 12,
    borderWidth: 1, borderColor: '#e6ee9c',
  },
  detailCol: { flex: 1 },
  detailText: { fontSize: 13, color: '#333', marginBottom: 4 },
  detailLabel: { fontWeight: 'bold', color: '#558b2f' },

  usesTitle: { fontSize: 14, fontWeight: 'bold', color: '#555', marginBottom: 4 },
  usesText: { fontSize: 15, color: '#333', lineHeight: 22, marginBottom: 12 },

  dosageContainer: { backgroundColor: '#f4fbf7', padding: 12, borderRadius: 10, marginBottom: 12, borderWidth: 1, borderColor: '#c8e6c9' },
  dosageTitle: { fontSize: 13, fontWeight: 'bold', color: '#2e7d32', marginBottom: 6, textTransform: 'uppercase' },
  dosageText: { fontSize: 14, color: '#2c3e2f', marginBottom: 4 },

  clinicalContainer: { backgroundColor: '#e8f4f8', padding: 12, borderRadius: 10, borderLeftWidth: 4, borderLeftColor: '#0277bd', marginBottom: 12 },
  clinicalTitle: { fontSize: 13, fontWeight: 'bold', color: '#0277bd', marginBottom: 6, textTransform: 'uppercase' },
  clinicalText: { fontSize: 14, color: '#01579b', lineHeight: 20 },

  nearbyContainer: { marginTop: 4, paddingTop: 12, borderTopWidth: 1, borderTopColor: '#eee' },
  nearbyTitle: { fontSize: 14, fontWeight: 'bold', color: '#00695c', marginBottom: 8 },
  locCard: { backgroundColor: '#e0f2f1', padding: 12, borderRadius: 10, marginBottom: 10, borderLeftWidth: 3, borderLeftColor: '#00897b' },
  nearbyImage: { width: '100%', height: 180, borderRadius: 8, marginBottom: 8, backgroundColor: '#b2dfdb' },
  locDesc: { fontWeight: 'bold', fontSize: 14, color: '#004d40', marginBottom: 4 },
  locNotes: { fontSize: 12, fontStyle: 'italic', color: '#00695c', marginBottom: 4 },
  locCoords: { fontSize: 11, color: '#00897b', marginBottom: 10 },

  directionsBtn: {
    backgroundColor: '#00897b', paddingVertical: 10, paddingHorizontal: 16,
    borderRadius: 10, alignItems: 'center', justifyContent: 'center',
    shadowColor: '#00897b', shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.3, shadowRadius: 5, elevation: 4,
  },
  directionsBtnDisabled: { backgroundColor: '#80cbc4' },
  directionsBtnText: { color: '#fff', fontWeight: 'bold', fontSize: 14 },
});
