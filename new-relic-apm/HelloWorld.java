public class HelloWorld {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("Hello from the New Relic Java demo app!");

        int counter = 0;
        while (true) {
            counter++;
            System.out.println(
                "[" + java.time.Instant.now() + "] still running... heartbeat #" + counter
            );
            // Keep the JVM alive so the agent has time to connect and report a harvest cycle.
            // (The agent's default harvest interval is ~60s.)
            Thread.sleep(10_000);
        }
    }
}
