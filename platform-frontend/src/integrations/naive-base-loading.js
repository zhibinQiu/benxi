import PlatformBaseLoading from "../components/PlatformBaseLoading.vue";

export const exposedLoadingProps = {
  strokeWidth: {
    type: Number,
    default: 28,
  },
  stroke: {
    type: String,
    default: undefined,
  },
  scale: {
    type: Number,
    default: 1,
  },
  radius: {
    type: Number,
    default: 100,
  },
};

export default PlatformBaseLoading;
