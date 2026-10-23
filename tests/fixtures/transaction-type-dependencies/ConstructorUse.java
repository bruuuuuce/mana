package fixture;
import org.springframework.stereotype.Service;
@Service class Entry {
    static class Helper { static void configure() {} }
    Entry() { Helper.configure(); }
    public void run() {}
}
